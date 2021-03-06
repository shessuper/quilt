#!/usr/bin/env python
# Copyright (c) 2013 Carnegie Mellon University.
# All Rights Reserved.
# Redistribution and use in source and binary forms, with or without 
# modification, are permitted provided that the following conditions are met:
# 1. Redistributions of source code must retain the above copyright notice, 
# this list of conditions and the following acknowledgments and disclaimers.
# 2. Redistributions in binary form must reproduce the above copyright notice, 
# this list of conditions and the following acknowledgments and disclaimers in 
# the documentation and/or other materials provided with the distribution.
# 3. Products derived from this software may not include "Carnegie Mellon 
# University," "SEI" and/or "Software Engineering Institute" in the name of 
# such derived product, nor shall "Carnegie Mellon University," "SEI" and/or 
# "Software Engineering Institute" be used to endorse or promote products 
# derived from this software without prior written permission. For written 
# permission, please contact permission@sei.cmu.edu.
# Acknowledgments and disclaimers:
# This material is based upon work funded and supported by the Department of 
# Defense under Contract No. FA8721-05-C-0003 with Carnegie Mellon University 
# for the operation of the Software Engineering Institute, a federally funded 
# research and development center. 
#  
# Any opinions, findings and conclusions or recommendations expressed in this 
# material are those of the author(s) and do not necessarily reflect the views 
# of the United States Department of Defense. 
#  
# NO WARRANTY. THIS CARNEGIE MELLON UNIVERSITY AND SOFTWARE ENGINEERING 
# INSTITUTE MATERIAL IS FURNISHEDON AN "AS-IS" BASIS.  CARNEGIE MELLON 
# UNIVERSITY MAKES NO WARRANTIES OF ANY KIND, EITHER EXPRESSED OR IMPLIED, AS 
# TO ANY MATTER INCLUDING, BUT NOT LIMITED TO, WARRANTY OF FITNESS FOR PURPOSE 
# OR MERCHANTABILITY, EXCLUSIVITY, OR RESULTS OBTAINED FROM USE OF THE 
# MATERIAL. CARNEGIE MELLON UNIVERSITY DOES NOT MAKE ANY WARRANTY OF ANY KIND 
# WITH RESPECT TO FREEDOM FROM PATENT, TRADEMARK, OR COPYRIGHT INFRINGEMENT. 
#  
# This material has been approved for public release and unlimited distribution.
#
# Carnegie Mellon(r), CERT(r) and CERT Coordination Center(r) are registered 
# marks of Carnegie Mellon University. 
#  
# DM-0000632
import sys
import logging
import quilt_core
from string import Template
import sei_core
import quilt_data
import Pyro4


class SourceManager(quilt_core.QueryMasterClient):
    def __init__(self, args, sourceName, sourceSpec):
        # chain to call super class constructor 
        quilt_core.QueryMasterClient.__init__(self, sourceName)
        self._args = args
        self._sourceName = sourceName
        self._sourceSpec = sourceSpec
        self._sourceResults = {}
        self._lastQuery = None


    def Query(self, queryId, sourceQuerySpec,
            queryClientName,
            queryClientNamseServerHost,
            queryClientNamseServerPort):
        """
        Query the source, currently hardcoded to behave as calling a cmdline
        tool that outputs source results on each output line
        """

        try:
            with self._lock:
                # set last query member to queryId
                self._lastQuery = queryId

            # _sourceName should not change, set at init, so ok to read
            # without lock
            logging.info("Source Manager: " + str(self._sourceName) +
                         " received query: " + str(queryId))

            # get the sourcePatternSpec from the pattern name in the
            #   sourceQuerySpec
            # pattern spec should be read only and safe to access without
            #   a lock
            srcPatSpecs = quilt_data.src_spec_get(self._sourceSpec,
                sourcePatterns=True)
            srcPatSpec = quilt_data.src_pat_specs_get(srcPatSpecs,
                quilt_data.src_query_spec_get(sourceQuerySpec,
                    srcPatternName=True))

            # get the variables in the query
            srcQueryVars = quilt_data.src_query_spec_get(sourceQuerySpec,
                variables=True)

            # iterate src query variables map, create a simple var name to
            #   var value map
            varNameValueDict = {}
            for srcVarName, srcVarSpec in srcQueryVars.items():
                varNameValueDict[srcVarName] = quilt_data.var_spec_get(
                    srcVarSpec, value=True)

            # create cmd line for the source
            # use the template in the sourcePatternSpec, and use the values
            #   provided for the variables, and environment variables
            replacements = {}
            # replacements = os.environ.copy()
            for k, v in varNameValueDict.items():
                replacements[k] = v

            # "template" was not added as official schema member because it is
            # specific to this command line case
            templateCmd = srcPatSpec['template']
            template = Template(templateCmd)
            logging.info("Ready to use : " + templateCmd +
                         " with replacements: " + str(replacements))
            cmdline = template.safe_substitute(replacements)

            # setup context for the cmdline stdout callback
            srcQueryId = quilt_data.src_query_spec_get(
                sourceQuerySpec, name=True)
            context = {'queryId': queryId, 'srcQueryId': srcQueryId}

            #           sei_core.run_process_lite(cmdline, shell=True,
            #               outFunc=self.OnGrepLine, outObj=context)

            #           I thought run_process apparently has problems
            sei_core.run_process(cmdline, shell=True,
                whichReturn=sei_core.EXITCODE,
                outFunc=self.OnGrepLine, outObj=context, logToPython=False)

            # Set query result events list in query master using query id
            results = []
            with self._lock:
                if queryId in self._sourceResults:
                    if srcQueryId in self._sourceResults[queryId]:
                        results = list(self._sourceResults[queryId][srcQueryId])

            uri = quilt_core.get_uri(queryClientNamseServerHost,
                queryClientNamseServerPort, queryClientName)

            with Pyro4.Proxy(uri) as query:
                query.AppendSourceQueryResults(srcQueryId, results)
                query.CompleteSrcQuery(srcQueryId)

                # catch exception!
        except Exception, error:
            try:

                # attempt to report error to the query client
                uri = quilt_core.get_uri(queryClientNamseServerHost,
                    queryClientNamseServerPort, queryClientName)
                srcQueryId = quilt_data.src_query_spec_get(
                    sourceQuerySpec, name=True)

                with Pyro4.Proxy(uri) as query:
                    query.OnSourceQueryError(srcQueryId, error)

            except Exception, error2:
                logging.error("Unable to send source query error to " +
                              "query master")
                logging.exception(error2)
            finally:
                logging.error("Failed to execute source query")
                logging.exception(error)


    def GetLastQuery(self):
        with self._lock:
            return self._lastQuery

    def OnGrepLine(self, line, contextData):
        # assemble a jason string for an object representing an event
        # based on eventSpec and eventSpec meta data
        # convert that string to a python event object
        # append event to list of events member
        queryId = contextData['queryId']
        srcQueryId = contextData['srcQueryId']
        srcRes = []
        with self._lock:

            # list in query master using query id and srcQuery Id

            if queryId not in self._sourceResults:
                queryRes = {}
                self._sourceResults[queryId] = queryRes
            else:
                queryRes = self._sourceResults[queryId]

            if srcQueryId not in queryRes:
                self._sourceResults[queryId][srcQueryId] = srcRes
            else:
                srcRes = self._sourceResults[queryId][srcQueryId]

        # only one source will be writing to the source event list at a
        #   time, so we can do so outside of the lock
        #TODO fix security problem with eval
        srcRes.append(eval(line))

    def GetType(self):
        return "smd"


    def GetSourcePatterns(self):
        """Returns a list of names of defined source patterns"""
        try:
            # non need to lock because no one should be writing to a source
            # spec
            # after init

            # iterate sourceSpec member's patterns
            # append returning list with pattern names
            srcPatSpecs = quilt_data.src_spec_tryget(self._sourceSpec,
                sourcePatterns=True)

            if srcPatSpecs is None:
                return []

            return srcPatSpecs.keys()

        # we log exception because this was likely called from another process
        except Exception, error:
            logging.exception(error)
            raise

    def GetSourcePattern(self, patternName):
        """return the specified source pattern specification dict"""
        # non need to lock because no one should be writing to a source spec
        # after init

        # access the source pattern spec with the specified key in the
        # sourceSpec, return a copy
        return quilt_data.src_pat_specs_get(quilt_data.src_spec_get(
            self._sourceSpec, sourcePatterns=True), patternName)


class Smd(quilt_core.QuiltDaemon):
    def __init__(self, args):
        quilt_core.QuiltDaemon.__init__(self)
        self.args = args
        self.setup_process("smd")

    def run(self):
        cfg = quilt_core.QuiltConfig()
        smspecs = cfg.GetSourceManagerSpecs()


        objs = {}
        # iterate through source manager configurations
        for smname, smspec in smspecs.items():
            logging.debug(smname + " specified from configuration")
            # create each source manager object
            sm = SourceManager(self.args, smname, smspec)
            objs[sm.localname] = sm


        # start the client with all the source managers
        quilt_core.query_master_client_main_helper(objs)


def main(argv):
    # setup command line interface
    parser = quilt_core.daemon_main_helper('smd', """Source manager
       daemon""",
        argv)

    args = parser.parse_args()

    # start the daemon
    Smd(args).main(argv)


if __name__ == "__main__":
    main(sys.argv[1:])

