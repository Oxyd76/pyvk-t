#! /usr/bin/python
# -*- coding: utf-8 -*-
import logging,os,sys
import pyvkt.component
import pyvkt.config as conf
import optparse

confName="pyvkt.cfg"
if(os.environ.has_key("PYVKT_CONFIG")):
    confName=os.environ["PYVKT_CONFIG"]
    
op=optparse.OptionParser()
op.add_option('-c','--config',default=confName, help='configuration file name')
op.add_option('-d','--admin-only',action='store_true', default=False, help='only admin can use transport when this flag is enabled')
op.add_option('-a','--autologin', action='store_true', default=False)
op.add_option('-l','--logfile', default=None, help='log file name')
op.add_option('-m','--logmode', default="warning", help='Log mode')

opt,args=op.parse_args()

LOG_LEVELS={'debug': logging.DEBUG,
            'info': logging.INFO,
            'warning': logging.WARNING,
            'error': logging.ERROR,
            'critical': logging.CRITICAL}
lvl=LOG_LEVELS.get(opt.logmode.lower(), logging.NOTSET)

LOG_FORMAT='    \033[32m* %(asctime)s\033[0m [%(levelname)3.3s] \033[33m%(funcName)12s\033[0m @ %(threadName)s:\t %(message).1000s'
logging.basicConfig(level=lvl,format=LOG_FORMAT)
if (opt.logfile):
    import logging.handlers
    logging.warning('writing log to %s'%opt.logfile)
    l=logging.getLogger('')
    rh=logging.handlers.RotatingFileHandler(opt.logfile,maxBytes=8000000,backupCount=5,encoding='utf-8')
    rh.setFormatter(logging.Formatter(LOG_FORMAT))
    l.addHandler(rh)
conf.read(opt.config)
#lvl=logging.WARNING
##FIXME logging options to optparse
#if ("--debug" in sys.argv):
    #lvl=logging.DEBUG
#if ("--info" in sys.argv):
    #lvl=logging.INFO

s=pyvkt.component.pyvk_t(conf.get("general","jid"))
if not s.connect(conf.get("general","server"),conf.get("general","port"),conf.get("general","secret")):
    logging.critical('can\'t connect')
else:
    logging.warn("connected")
    if (opt.autologin):
        s.addResource(conf.get("general","admin"))
    if (opt.admin_only):
        print "isActive=0"
        s.isActive=0
    s.startPoll()
    try:
        s.main()
    except KeyboardInterrupt:
        s.term()
