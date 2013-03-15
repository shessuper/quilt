#!/usr/bin/env python
import re
import os
import time
import ConfigParser
import logging
from os import listdir
from os.path import isfile, join

class QuiltConfig:
    """Responsible for access to quilt configuration"""

    # The name of the environment variable that defines the location
    # of the quilt config directory.  This will be the filesystem path to a
    # directory containing a quilt.cfg file.  ALso it may have a smd.d
    # subdirectory where sourcemaster configurations may be
    QUILT_CFG_DIR_VAR='QUILT_CFG_DIR'

    # ConfigParser for quilt.cfg
    _config = None

    def GetCfgDir(self):
        """Get the configuration dir which is to contain config files"""
        # default configuration location to /etc/quilt
        cfgdir = '/etc/quilt'
        
        # if QUILT_CFG_DIR_VAR set, set location off of that value
        if QUILT_CFG_DIR_VAR in os.environ:
            cfgdir = os.environ[QUILT_CFG_DIR_VAR]        

    def __init__(self):
        """Construct the object, read in the main quilt.cfg file"""
       
        # if config file exists at location, read it in
        quiltcfg = os.path.join(GetCfgDir(), 'quilt.cfg')

        if not os.path.exists(quiltcfg):
            raise Exception("quilt config not found at: " + quiltcfg)

        self._config = Config.ConfigParser()
        self._config.read(quiltcfg)

    def GetValue(        # [out] string
        self,
        sectionName,     # [in] string, name of section
        valueName,       # [in] string, name of value
        default)         # [in] value of default
        """Access a configuration value.  Configuraiton values can be
        specified with a section and a name.  The configuration value is
        returned.  If the specified value is not present the passed in
        default is returned."""
       
        if self._config.has_optiony(sectionName,valueName):
            return self._config.get(sectionName,valueName)

        return default


    def GetSourceManagers(self)
        """get list of all defined source managers"""
    
        # iterate through the source managers defined in the configuration
        smdcfgdir = self.GetValue('source_managers', 'config_dir',
            os.path.join(self.GetCfgDir(), 'smd.d'))

        smdcfgdir = os.path.expandvars(smdcfgdir)        
        if not path.exists(smdcfgdir):
            logging.warning(
                "Source Manager config file directory does not exist" +
                smdcfgdir)
        
        smdcfgs = [ f for f in listdir(smdcfgdir) 
            if isfile(join(smdcfgdir,f)) ]

        # read all sections from all config file sin the smd directory
        smdnames = []
        for f in smdcfgs:
            c = ConfigParser.ConfigParser()
            c.read(join(smdcfgdir, f)
                for s in c.sections():
                    smdnames.append(s)
        return smdnames
                    

    
    
    def static query_master_client_main_helper(
            clientObjectDict       # map of instances to names of objects to
                                   # host as pyro objects
        ):
        """Used to publish the client as a remote object, and complete the
        connection with the query master"""

        # Use QuiltConfig to read in configuration
        cfg = QuiltConfig()
        # access the registrar's host and port number from config
        registrarHost = cfg.GetValue(
            'registrar', 'registrar_host', 'localhost')
        registrarPort = cfg.GetValue(
            'registrar', 'registrar_port', None) 
        
        daemon=Pyro4.Daemon()
        ns=Pyro4.locateNS(registrarHost, registrarPort)   
        # iterate the names and objects in clientObjectDict
        for name,obj in clientObjectDict:
            # register the clientObject with the local PyRo Daemon with
            uri=daemon.register(obj)
            # use the key name as the object name
            ns.register(name,uri)
            # call the ConnectToQueryMaster to complete registration
            obj.ConnectToQueryMaster()
            
        # start the Daemon's event loop
        daemon.requestLoop() 


        
