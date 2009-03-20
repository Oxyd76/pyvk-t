# -*- coding: utf-8 -*-

"""
 Example component service.
 
"""
import time
import twisted
from twisted.words.protocols.jabber import jid, xmlstream
from twisted.application import internet, service
from twisted.internet import interfaces, defer, reactor,threads
from twisted.python import log
from twisted.words.xish import domish
from twisted.words.protocols.jabber.xmlstream import IQ
from twisted.enterprise import adbapi 
from twisted.enterprise.adbapi import safe 

from twisted.words.protocols.jabber.ijabber import IService
from twisted.words.protocols.jabber import component,xmlstream
from libvkontakte import *
from zope.interface import Interface, implements
import ConfigParser
from twisted.internet import defer
from twisted.python.threadpool import ThreadPool
import sys,os,cPickle
from base64 import b64encode,b64decode
import pyvkt_commands
from pyvkt_user import user
import pyvkt_global as pyvkt
#try:
    #from twisted.internet.threads import deferToThreadPool
#except:
from pyvkt_spikes import deferToThreadPool
def create_reply(elem):
    """ switch the 'to' and 'from' attributes to reply to this element """
    # NOTE - see domish.Element class to view more methods 
    frm = elem['from']
    elem['from'] = elem['to']
    elem['to']   = frm

    return elem

class LogService(component.Service):
    """
    A service to log incoming and outgoing xml to and from our XMPP component.

    """
    
    def transportConnected(self, xmlstream):
        xmlstream.rawDataInFn = self.rawDataIn
        xmlstream.rawDataOutFn = self.rawDataOut

    def rawDataIn(self, buf):
        #log.msg("%s - RECV: %s" % (str(time.time()), unicode(buf, 'utf-8').encode('ascii', 'replace')))
        pass

    def rawDataOut(self, buf):
        #log.msg("%s - SEND: %s" % (str(time.time()), unicode(buf, 'utf-8').encode('ascii', 'replace')))
        pass

def bareJid(jid):
    n=jid.find("/")
    if (n==-1):
        return jid.lower()
    return jid[:n].lower()

class pyvk_t(component.Service,vkonClient):

    implements(IService)

    def __init__(self):
        config = ConfigParser.ConfigParser()
        confName="pyvk-t_new.cfg"
        if(os.environ.has_key("PYVKT_CONFIG")):
            confName=os.environ["PYVKT_CONFIG"]
        config.read(confName)
        dbmodule=config.get("database","module") 
        if dbmodule=="MySQLdb":
            self.dbpool = adbapi.ConnectionPool(
                dbmodule,
                host=config.get("database","host"), 
                user=config.get("database","user"), 
                passwd=config.get("database","passwd"), 
                db=config.get("database","db"),
                cp_reconnect=1)
        elif dbmodule=="sqlite3":
            self.dbpool = adbapi.ConnectionPool(
                dbmodule,
                database=config.get("database","db"),
                cp_reconnect=1)
        else:
            self.dbpool = adbapi.ConnectionPool(
                dbmodule,
                host=config.get("database","host"), 
                user=config.get("database","user"), 
                password=config.get("database","passwd"), 
                database=config.get("database","db"),
                cp_reconnect=1)

            
        if config.has_option("features","sync_status"):
            self.sync_status = config.getboolean("features","sync_status")
        else:
            self.sync_status = 0
        if config.has_option("features","avatars"):
            self.show_avatars = config.getboolean("features","avatars")
        else:
            self.show_avatars = 0

        self.users={}
        try:
            self.admin=config.get("general","admin")
        except:
            log.message("you didn't set admin JID in config!")
            self.admin=None
        #self.config=config
        #try:
        proc=os.popen("svnversion")
        s=proc.read()
        if(s=="exported" or s==""):
            self.revision="alpha"
        else:
            p=s.find(":")
            ver=s[p+1:-1]
            self.revision="svn rev. %s"%ver
        #self.commands=pyvktCommands(self)
        self.commands=pyvkt_commands.cmdManager(self)
        #except:
            #log.msg("can't ret revision")
            #self.revision="alpha"
        self.isActive=1
        #self.commands=
        # FIXME 
    def jidToId(self,jid):
        dogpos=jid.find("@")
        if (dogpos==-1):
            return 0
        try:
            v_id=int(jid[:dogpos])
            return v_id
        except:
            return -1
    def componentConnected(self, xmlstream):
        """
        This method is called when the componentConnected event gets called.
        That event gets called when we have connected and authenticated with the XMPP server.
        """
        
        self.jabberId = xmlstream.authenticator.otherHost
        self.jid= xmlstream.authenticator.otherHost
        self.xmlstream = xmlstream # set the xmlstream so we can reuse it
        
        xmlstream.addObserver('/presence', self.onPresence, 1)
        xmlstream.addObserver('/iq', self.onIq, 1)
        #xmlstream.addOnetimeObserver('/iq/vCard', self.onVcard, 2)
        xmlstream.addObserver('/message', self.onMessage, 1)

    def onMessage(self, msg):
        """
        Act on the message stanza that has just been received.

        """
        v_id=self.jidToId(msg["to"])
        if (v_id==-1):
            return None
        if (msg.body):
            body=msg.body.children[0]
            bjid=bareJid(msg["from"])
            if (body[0:1]=="/") and body[:4]!="/me ":
                cmd=body[1:]
                #if (self.users.has_key(bjid) and self.users[bjid].thread and cmd=="get roster"):
                if (self.hasUser(bjid) and cmd=="get roster"):
                    d=defer.execute(self.users[bjid].thread.getFriendList)
                    d.addCallback(self.sendFriendlist,jid=bjid)
                elif (cmd=="help"):
                    self.sendMessage(self.jid,msg["from"],u"/get roster для получения списка\n/login для подключения")
                else:
                    
                    if (self.hasUser(bjid)):
                        d=deferToThreadPool(reactor,self.users[bjid].pool,f=self.commands.onMsg,jid=bjid,text=cmd,v_id=v_id)
                    else:
                        d=threads.deferToThread(f=self.commands.onMsg,jid=bjid,text=cmd,v_id=v_id)
                    cb=lambda (x):self.sendMessage(msg['to'],msg["from"],x)
                    d.addCallback(cb)
                return

            if (body[0:1]=="#" and bjid==self.admin and msg["to"]==self.jid):
                # admin commands
                cmd=body[1:]
                
                log.msg("admin command: '%s'"%cmd)
                if (cmd=="stop"):
                    self.isActive=0
                    self.stopService()
                    self.sendMessage(self.jid,msg["from"],"'%s' done"%cmd)
                elif (cmd=="start"):
                    self.isActive=1
                elif (cmd=="stats"):
                    ret=u"%s user(s) online"%len(self.users)
                    for i in self.users:
                        if (self.hasUser(i)):
                            ret=ret+u"\nxmpp:%s"%i
                    self.sendMessage(self.jid,msg["from"],ret)
                elif (cmd[:4]=="wall"):
                    for i in self.users:
                        self.sendMessage(self.jid,i,"[broadcast message]\n%s"%cmd[5:])
                    self.sendMessage(self.jid,msg["from"],"'%s' done"%cmd)
                else:
                    self.sendMessage(self.jid,msg["from"],"unknown command: '%s'"%cmd)
                return
            if(msg["to"]!=self.jid and self.hasUser(bjid)):
                dogpos=msg["to"].find("@")
                try:
                    v_id=int(msg["to"][:dogpos])
                except:
                    log.msg("bad JID: %s"%msg["to"])
                    return
                req=msg.request
                #if hasAttribute(msg,"title"):
                    #title = msg.title
                #else:
                #FIXME
                title = "xmpp:%s"%bjid
                if(req==None):
                    print "legacy message"
                    self.users[bjid].pool.callInThread(self.submitMessage,jid=bjid,v_id=v_id,body=body,title=title)
                else:
                    if (req.uri=='urn:xmpp:receipts'):

                        #old versions of twisted does not have deferToThreadPool function
                        # FIXED
                        d=deferToThreadPool(
                                reactor=reactor,
                                threadpool=self.users[bjid].pool,
                                f=self.users[bjid].thread.sendMessage,to_id=v_id,body=body,title=title)
                        d.addCallback(self.msgDeliveryNotify,msg_id=msg["id"],jid=msg["from"],v_id=v_id)
                
            #TODO delivery notification
    def msgDeliveryNotify(self,res,msg_id,jid,v_id):
        """
        Send delivery notification if message successfully sent
        """
        msg=domish.Element((None,"message"))
        msg["to"]=jid
        msg["from"]="%s@%s"%(v_id,self.jid)
        msg["id"]=msg_id
        if res == 0:
            msg.addElement("received",'urn:xmpp:receipts')
        elif res == 2:
            err = msg.addElement("error")
            err.attributes["type"]="wait"
            err.attributes["code"]="400"
            err.addElement("unexpected-request","urn:ietf:params:xml:ns:xmpp-stanzas")
            err.addElement("too-many-stanzas","urn:xmpp:errors")
        else:
            err = msg.addElement("error")
            err.attributes["type"]="cancel"
            err.attributes["code"]="500"
            err.addElement("undefined-condition","urn:ietf:params:xml:ns:xmpp-stanzas")
        self.xmlstream.send(msg)

    def onIq(self, iq):
        """
        Act on the iq stanza that has just been received.
        """
        #log.msg(iq["type"])
        #log.msg(iq.firstChildElement().toXml().encode("utf-8"))
        bjid=bareJid(iq["from"])
        if (iq["type"]=="get"):
            query=iq.query
            if (query):
                ans=xmlstream.IQ(self.xmlstream,"result")
                ans["to"]=iq["from"]
                ans["from"]=iq["to"]
                ans["id"]=iq["id"]
                q=ans.addElement("query",query.uri)
                if (query.uri=="http://jabber.org/protocol/disco#info"):
                    if (query.hasAttribute("node")):
                        self.xmlstream.send(self.commands.onDiscoInfo(iq))
                        return
                    else:
                        if (iq["to"]==self.jid):
                            q.addElement("identity").attributes={"category":"gateway","type":"vkontakte.ru","name":"Vkontakte.ru transport [twisted]"}
                            q.addElement("feature")["var"]="jabber:iq:register"
                            q.addElement("feature")["var"]="jabber:iq:gateway"
                            if (self.hasUser(bjid)):
                                q.addElement("feature")["var"]="jabber:iq:search"
                            q.addElement("feature")["var"]='http://jabber.org/protocol/commands'
                            #q.addElement("feature")["var"]="stringprep"
                            #q.addElement("feature")["var"]="urn:xmpp:receipts"
                        else:
                            q.addElement("identity").attributes={"category":"pubsub","type":"pep"}
                            #q.addElement("feature")["var"]="stringprep"
                            q.addElement("feature")["var"]='http://jabber.org/protocol/commands'
                            q.addElement("feature")["var"]="urn:xmpp:receipts"
                        ans.send()
                        return
                elif (query.uri=="http://jabber.org/protocol/disco#items"):
                    if (query.hasAttribute("node")):
                        q["node"]=query["node"]
                        if (query["node"]=="http://jabber.org/protocol/commands"):
                            self.xmlstream.send(self.commands.onDiscoItems(iq))
                            return
                    ans.send()
                    return
                elif (query.uri=="jabber:iq:register"):
                    q.addElement("instructions").addContent(u"Введите email и пароль, используемые на vkontakte.ru")
                    q.addElement("email")
                    q.addElement("password")
                    ans.send()
                    return
                elif (query.uri=="jabber:iq:version"):
                    q.addElement("name").addContent("pyvk-t [twisted]")
                    q.addElement("version").addContent(self.revision)
                    ans.send()
                    return
                elif (query.uri=="jabber:iq:gateway"):
                    q.addElement("desc").addContent(u"Пожалуйста, введите id ползователя на сайте вконтакте.ру.\nУзнать, какой ID у пользователя Вконтакте можно, например, так:\nЗайдите на его страницу. В адресной строке будет http://vkontakte.ru/profile.php?id=0000000\nЗначит его ID - 0000000")
                    q.addElement("prompt").addContent("Vkontakte ID")
                    ans.send()
                    return
                elif (query.uri=="jabber:iq:search" and self.hasUser(bjid)):
                    q.addElement("instructions").addContent(u"Use the enclosed form to search. If your Jabber client does not support Data Forms, visit http://shakespeare.lit/")
                    x=q.addElement("x","jabber:x:data")
                    x['type']='form'
                    x.addElement("instructions").addContent(u"Введите произвольный текст по которому будет произведен поиск")
                    hidden=x.addElement("field")
                    hidden['type']='hidden'
                    hidden['var']='FORM_TYPE'
                    hidden.addElement('value').addContent(u'jabber:iq:search')
                    text=x.addElement("field")
                    text['type']='text-single'
                    text['label']=u'Текст'
                    text['var']='text'
                    ans.send()
                    return
                    
            vcard=iq.vCard
            if (vcard):
                dogpos=iq["to"].find("@")
                if(dogpos!=-1):
                    try:
                        v_id=int(iq["to"][:dogpos])
                    except:
                        log.msg("bad JID: %s"%iq["to"])
                        pass
                    else:
                        #log.msg("id: %s"%v_id)
                        if (self.hasUser(bjid)):
                            #self.users[bjid].pool.callInThread(time.sleep(1))
                            self.users[bjid].pool.callInThread(self.getsendVcard,jid=iq["from"],v_id=v_id,iq_id=iq["id"])
                            return
                        else:
                            print("thread not found: %s"%bjid)
                else:
                    ans=xmlstream.IQ(self.xmlstream,"result")
                    ans["to"]=iq["from"]
                    ans["from"]=iq["to"]
                    ans["id"]=iq["id"]
                    q=ans.addElement("vCard","vcard-temp")
                    q.addElement("FN").addContent("vkontakte.ru transport")
                    q.addElement("URL").addContent("http://pyvk-t.googlecode.com")
                    q.addElement("DESC").addContent("Vkontakte.ru jabber transport\nVersion: %s"%self.revision)
                    if self.show_avatars:
                        try:
                            req=open("avatar.png")
                            photo=base64.encodestring(req.read())
                            p=q.addElement(u"PHOTO")
                            p.addElement("TYPE").addContent("image/png")
                            p.addElement("BINVAL").addContent(photo.replace("\n",""))
                        except:
                            print 'cannot load avatar'
                    ans.send()
                    return
                    
        if (iq["type"]=="set"):
            query=iq.query
            if (query):
                if (query.uri=="jabber:iq:register"):
                    if (query.remove):
                        qq=self.dbpool.runQuery("DELETE FROM users WHERE jid='%s';"%safe(bareJid(iq["from"])))
                        return
                    log.msg("from %s"%bareJid(iq["from"]))
                    log.msg(query.toXml())
                    email=""
                    pw=""
                    for i in filter(lambda x:type(x)==twisted.words.xish.domish.Element,query.children):
                        log.msg(i)
                        if (i.name=="email"):
                            email=i.children[0]
                        if (i.name=="password"):
                            pw=i.children[0]
                    qq=self.dbpool.runQuery("DELETE FROM users WHERE jid='%s';INSERT INTO users (jid,email,pass) VALUES ('%s','%s','%s');"%
                        (safe(bareJid(iq["from"])),safe(bareJid(iq["from"])),safe(email),safe(pw)))
                    qq.addCallback(self.register2,jid=iq["from"],iq_id=iq["id"],success=1)
                    return
                if (query.uri=="jabber:iq:gateway"):
                    for prompt in query.elements():
                        if prompt.name=="prompt":
                            ans=xmlstream.IQ(self.xmlstream,"result")
                            ans["to"]=iq["from"]
                            ans["from"]=iq["to"]
                            ans["id"]=iq["id"]
                            q=ans.addElement("query",query.uri)
                            q.addElement("jid").addContent("%s@%s"%(prompt,iq["to"]))
                            ans.send()
                            return
                elif (query.uri=="jabber:iq:search") and (self.hasUser(bjid)):
                        time.sleep(1)
                        self.users[bjid].pool.callInThread(self.getSearchResult,jid=iq["from"],q=query,iq_id=iq["id"])
                        return

            cmd=iq.command
            if (cmd):
                if (self.hasUser(bjid)):
                    d=deferToThreadPool(reactor,self.users[bjid].pool,f=self.commands.onIqSet,iq=iq)
                else:
                    d=threads.deferToThread(f=self.commands.onIqSet,iq=iq)
                d.addCallback(self.xmlstream.send)
                return
        iq = create_reply(iq)
        iq["type"]="error"
        err=iq.addElement("error")
        err["type"]="cancel"
        err.addElement("feature-not-implemented","urn:ietf:params:xml:ns:xmpp-stanzas")
        #print iq
        self.xmlstream.send(iq)

    def register2(self,qres,jid,iq_id,success):
        #FIXME failed registration
        ans=xmlstream.IQ(self.xmlstream,"result")
        ans["to"]=jid
        ans["from"]=self.jid
        ans["id"]=iq_id
        ans.send()
        pr=domish.Element(('',"presence"))
        pr["type"]="subscribe"
        pr["to"]=jid
        pr["from"]=self.jid
        self.xmlstream.send(pr)
        pr=domish.Element(('',"presence"))
        pr["type"]="subscribed"
        pr["to"]=jid
        pr["from"]=self.jid
        self.xmlstream.send(pr)
        self.sendMessage(self.jid,jid,u"/get roster для получения списка\n/login дла подключения")

    def sendFriendlist(self,fl,jid):
        #log.msg("fiendlist ",jid)
        #log.msg(fl)
        for f in fl:
            src="%s@%s"%(f,self.jid)
            log.msg(src)
            #self.sendPresence(src,jid,"subscribed")
            self.sendPresence(src,jid,"subscribe")
            #return
        return

    def getSearchResult(self,jid,q,iq_id):
        """
        Send a search result we got from libvkontakte
        """
        ans=xmlstream.IQ(self.xmlstream,"result")
        ans["to"]=jid
        ans["from"]=self.jid
        ans["id"]=iq_id
        query=ans.addElement("query","jabber:iq:search")

        correct = 0
        text=u''
        for x in q.elements():
            if x.uri=='jabber:x:data' and x.hasAttribute('type') and x['type']=='submit':
                for j in x.elements():
                    if j.name=='field' and j.hasAttribute('var') and j['var']=='FORM_TYPE':
                        for v in j.elements():
                            if v.name=='value' and v.__str__()=='jabber:iq:search':
                                correct = 1
                                break
                    elif j.name=='field' and j.hasAttribute('var') and j['var']=='text':
                        for v in j.elements():
                            if v.name=='value':
                                text = v.__str__()
                                break
            if not correct: 
                text=u''
            else:
                break
        bjid=bareJid(jid)
        try:
            if text: 
                items=self.users[bjid].thread.searchUsers(text)
                if items:
                    x=query.addElement("x","jabber:x:data")
                    x['type']='result'
                    hidden=x.addElement("field")
                    hidden['type']='hidden'
                    hidden['var']='FORM_TYPE'
                    hidden.addElement('value').addContent(u'jabber:iq:search')
                    item=x.addElement("reported")
                    field=item.addElement("field")
                    field['type']='text-single'
                    field['label']=u'Jabber ID'
                    field['var']='jid'
                    field=item.addElement("field")
                    field['type']='text-single'
                    field['label']=u'Полное имя'
                    field['var']='FN'
                    field=item.addElement("field")
                    field['type']='text-single'
                    field['label']=u'Страница Вконтакте'
                    field['var']='vk.ru'
                    for i in items:
                        item=x.addElement("item")
                        field=item.addElement("field")
                        field['var']='jid'
                        field.addElement("value").addContent(i+u'@'+self.jid)
                        field=item.addElement("field")
                        field['var']='FN'
                        field.addElement("value").addContent(items[i])
                        field=item.addElement("field")
                        field['var']='vk.ru'
                        field.addElement("value").addContent(u"http://vkontakte.ru/id%s"%i)
        except:
            log.msg("some fcky error when searching")
        #log.msg(card)
        ans.send()


    def getsendVcard(self,jid,v_id,iq_id):
        """
        get vCard (user info) from vkontakte.ru and send it
        """
        #log.msg(jid)
        #log.msg(v_id)
        bjid=bareJid(jid)
        #try:
        card=self.users[bjid].thread.getVcard(v_id, self.show_avatars)
        #except:
            #log.msg("some fcky error")
            #card = None

        #log.msg(card)
        ans=xmlstream.IQ(self.xmlstream,"result")
        ans["to"]=jid
        ans["from"]="%s@%s"%(v_id,self.jid)
        ans["id"]=iq_id
        vc=ans.addElement("vCard","vcard-temp")
        #if some card set
        if (card):
            #convert to unicode if needed
            for i in card:
                if (type(card[i])==type('')):
                    card[i]=card[i].decode("utf-8")
            if card.has_key("NICKNAME"):
                vc.addElement("NICKNAME").addContent(card["NICKNAME"])
            if card.has_key("FAMILY") or card.has_key("GIVEN"):
                n=vc.addElement("N")
                if card.has_key("FAMILY"):
                    n.addElement("FAMILY").addContent(card["FAMILY"])
                if card.has_key("GIVEN"):
                    n.addElement("GIVEN").addContent(card["GIVEN"])
            if card.has_key("FN"):
                vc.addElement("FN").addContent(card["FN"])
            if card.has_key(u'Веб-сайт:'):
                vc.addElement("URL").addContent(card[u"Веб-сайт:"])
            if card.has_key(u'День рождения:'):
                vc.addElement("BDAY").addContent(card[u"День рождения:"])
            #description
            descr=u""
            for x in (u"Деятельность:",
                      u"Интересы:",
                      u"Любимая музыка:",
                      u"Любимые фильмы:",
                      u"Любимые телешоу:",
                      u"Любимые книги:",
                      u"Любимые игры:",
                      u"Любимые цитаты:"):
                if card.has_key(x):
                    descr+=x+u'\n'
                    descr+=card[x]
                    descr+=u"\n\n"
            if card.has_key(u'О себе:'):
                if descr: descr+=u"О себе:\n"
                descr+=card[u"О себе:"]
                descr+=u"\n\n"
            descr+="http://vkontakte.ru/id%s"%v_id
            descr=descr.strip()
            if descr:
                vc.addElement("DESC").addContent(descr)
            #phone numbers
            if card.has_key(u'Дом. телефон:'):
                tel = vc.addElement("TEL")
                tel.addElement("HOME")
                tel.addElement("NUMBER").addContent(card[u"Дом. телефон:"])
            if card.has_key(u'Моб. телефон:'):
                tel = vc.addElement(u"TEL")
                tel.addElement("CELL")
                tel.addElement("NUMBER").addContent(card[u"Моб. телефон:"])
            #avatar
            if card.has_key(u'PHOTO') and self.show_avatars:
                photo=vc.addElement(u"PHOTO")
                photo.addElement("TYPE").addContent("image/jpeg")
                photo.addElement("BINVAL").addContent(card[u"PHOTO"].replace("\n",""))
            #adress
            if card.has_key(u'Город:'):
                vc.addElement(u"ADR").addElement("LOCALITY").addContent(card[u"Город:"])
        else:
            vc.addElement("DESC").addContent("http://vkontakte.ru/id%s"%v_id)
        ans.send()
            #log.msg(ans.toXml())

    def requestMessage(self,jid,msgid):
        print "msg request"
        bjid=jid
        msg=self.users[bjid].thread.getMessage(msgid)
        #log.msg(msg)
        print msg
        self.sendMessage("%s@%s"%(msg["from"],self.jid),jid,msg["text"])

    def submitMessage(self,jid,v_id,body,title):
        #log.msg((jid,v_id,body,title))
        bjid=jid
        try:
            self.users[bjid].thread.sendMessage(to_id=v_id,body=body,title=title)
        except:
            print "submit failed"

    def updateStatus(self, bjid, text):
        """
        update site stuse if enabled
        """
        if self.hasUser(bjid) and self.sync_status:
            print "updating status for",bjid,":",text.encode("ascii","replace")
            self.users[bjid].thread.setStatus(text)
    def hasUser(self,bjid):
        #print "hasUser (%s)"%bjid
        if (self.users.has_key(bjid)):
            if (self.users[bjid].active):
                return 1
            else:
                del self.users[bjid]
        return 0
    def addResource(self,jid,prs=None):
        #print "addRes"
        bjid=pyvkt.bareJid(jid)
        if (self.hasUser(bjid)==0):
            #print "creating user %s"
            self.users[bjid]=user(self,jid)
        self.users[bjid].addResource(jid,prs)
    def delResource(self,jid):
        #print "delResource %s"%jid
        bjid=pyvkt.bareJid(jid)
        if (self.hasUser(bjid)):
            #TODO resource magic
            self.users[bjid].delResource(jid)
    def onPresence(self, prs):
        """
        Act on the presence stanza that has just been received.
        """
        #return
        bjid=bareJid(prs["from"])
        if(prs.hasAttribute("type")):
            if prs["type"]=="unavailable":
                #if self.hasReource(bjid):
                    #del self.resources[bjid]
                self.delResource(prs["from"])
                pr=domish.Element(('',"presence"))
                pr["type"]="unavailable"
                pr["to"]=bjid
                pr["from"]=self.jid
                self.xmlstream.send(pr)
            elif(prs["type"]=="subscribe"):
                self.sendPresence(prs["to"],prs["from"],"subscribed")
            return
        #if (prs["to"]==self.jid):
        if (self.isActive or bjid==self.admin):
            self.addResource(prs["from"],prs)
    def feedChanged(self,jid,feed):
        ret=""
        for k in feed.keys():
            if (k!="user" and feed[k]["count"]):
                ret=ret+"new %s: %s\n"%(k,feed[k]["count"])
        #try:
        if (feed["messages"]["count"] ):
            for i in feed ["messages"]["items"].keys():
                print "requesting message"
                self.users[jid].pool.callInThread(self.requestMessage,jid=jid,msgid=i)
            #if (feed["groups"]["count"]):
                #for i in feed["groups"]["items"]:
                    #ret=ret+"\n"+feed["groups"]["items"][i]+" [http://vkontakte.ru/club%s]"%i
        #except KeyError:
            #log.msg("feed error")
        self.sendPresence(self.jid,jid,status=ret)
    def usersOnline(self,jid,users):
        for i in users:
            self.sendPresence("%s@%s"%(i,self.jid),jid)
    def usersOffline(self,jid,users):
        for i in users:
            self.sendPresence("%s@%s"%(i,self.jid),jid,t="unavailable")
    def threadError(self,jid,err):
        if (err=="banned"):
            self.sendMessage(self.jid,jid,u"Слишком много запросов однотипных страниц.\nКонтакт частично заблокировал доступ на 10-15 минут. На всякий случай, транспорт отключается")
        elif(err=="auth"):
            self.sendMessage(self.jid,jid,u"Ошибка входа. Возможно, неправильный логин/пароль.")
        try:
            self.users[i].logout()
        except:
            pass
        self.sendPresence(self.jid,jid,"unavailable")
    def stopService(self):
        print "logging out..."
        for u in self.users:
            self.users[u].logout()
            self.sendMessage(self.jid,u,u"Транспорт отключается, в ближайшее время он будет запущен вновь.")
            self.sendPresence(self.jid,u,"unavailable")
        time.sleep(15)
        print "done"
        return None
    def saveConfig(self,bjid):
        try:
            pcs=b64encode(cPickle.dumps(self.users[bjid].config))
        except KeyError:
            print "keyError"
            return -1
        q="UPDATE users SET config = '%s' WHERE jid = '%s';"%(safe(pcs),safe(bjid))
        print q
        qq=self.dbpool.runQuery(q)
        return 0
    def sendMessage(self,src,dest,body):
        msg=domish.Element((None,"message"))
        #try:
            #msg["to"]=dest.encode("utf-8")
        #except:
            #log.msg("sendMessage: possible charset error")
        msg["to"]=dest
        msg["from"]=src
        msg["type"]="chat"
        msg["id"]="msg%s"%(int(time.time())%10000)
        
        msg.addElement("body").addContent(body)
        
        #FIXME "id"???
        try:
            self.xmlstream.send(msg)
        except UnicodeDecodeError:
            #FIXME user notify
            log.msg("unicode bug@sendMessage")
            try:
                print "jid: "%dest
            except:
                pass
            pass
    def sendPresence(self,src,dest,t=None,extra=None,status=None,show=None):
        pr=domish.Element((None,"presence"))
        if (t):
            pr["type"]=t
        #try:
        pr["to"]=dest
        #except:
            #log.msg("sendPresence: possible charset error")
            #pr["to"]=dest
        pr["from"]=src
        if(show):
            pr.addElement("show").addContent(show)
        pr["ver"]=self.revision
        if(status):
            pr.addElement("status").addContent(status)
        pr.addElement("c","http://jabber.org/protocol/caps").attributes={"node":"http://pyvk-t.googlecode.com/caps","ver":self.revision}
        try:
            self.xmlstream.send(pr)
        except UnicodeDecodeError:
            log.msg("unicode bug@sendPresence")
            try:
                print "jid: "%dest
            except:
                pass
            pass
    def __del__(self):
        print "stopping service..."
        self.stopService()
        print "done"

