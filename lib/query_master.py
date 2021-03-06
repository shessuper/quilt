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


import logging
import Pyro4
import threading
import pprint
import quilt_data
import quilt_parse
import quilt_core
import os
import subprocess
import var_dict


class QueryMaster:
    def __init__(self, args):
        self._args = args
        self.clients = {}
        self._queries = quilt_data.query_specs_create()
        self._history = quilt_data.query_specs_create()
        self._patterns = quilt_data.pat_specs_create()
        self.lock = threading.Lock()

    def RegisterClient(
            self,
            nameServerHost,
            nameServerPort,
            clientName,
            clientType):
        """
        Register a client with the query master
        string RegisterClient(   # return key name for the client
            string nameServerHost,      # ip address of nameserver
            int nameServerPort,         # port for the nameserver
            string clientName           # name of the source manager on
                                        # the specified nameserver
            string clientType           # name of the type of the client
        """
        with self.lock:

            # get the proxy handle to the remote object 

            # determine unique name for client (hopefully just using the
            # passed in name, but double check registered list.
            uniqueName = clientName
            index = 1
            if clientType not in self.clients:
                self.clients[clientType] = {}

            while uniqueName in self.clients[clientType]:
                uniqueName = '_'.join([clientName, str(index)])
                index += 1

            # Store in list of registered clients
            # use object's name and type to key it in the registered list
            self.clients[clientType][uniqueName] = {
                'registrarHost': nameServerHost,
                'registrarPort': nameServerPort,
                'clientName': clientName}


            # return the determined name
            logging.debug("Registered client: " + uniqueName)
            return uniqueName

    def UnRegisterClient(
            self,
            clientType,
            clientNameKey):
        """
        UnRegister a client with the query master
         string clientType - part of key
         string clientNameKey - key that the qmd knows to id a client
        """
        with self.lock:
            # if not found in the list, do nothing
            if clientType not in self.clients:
                return
            if clientNameKey not in self.clients[clientType]:
                return
            logging.debug("Unregistering client: " + clientNameKey + "...")
            clientDict = self.clients[clientType][clientNameKey]
            # remove the specified sm from registered list
            del self.clients[clientType][clientNameKey]

        # client not found log warning
        if clientDict is None:
            logging.warn("Attempted to unregister client: " + clientNameKey +
                         ", but client not found")


    def GetSourceManagerStats(self):
        """
        format a string with information about all source managers
        describe all of the source managers, and return as string 
        """
        # Get Clients is thread safe
        smgrs = self.GetClients("smd")

        if smgrs is None:
            return "0 source managers"

        # iterate source managers, gather nfo
        s = str(len(smgrs)) + " source manager(s): \n" + pprint.pformat(smgrs)

        return s

    def GetClients(self, objType):
        """return the list of registered clients matching the specified
        type"""

        clients = []
        with self.lock:
            if objType in self.clients:
                clients = self.clients[objType].copy()

        return clients

    def GetClientRec(self, objType, clientName):
        """return the master's client record for the specified client"""
        with self.lock:
            return self.clients[objType][clientName].copy()

    def DefinePattern(self, patternSpec):
        """Define the specified pattern in the query master, return
        the finalized (unique) name of the pattern"""

        try:
            # determine unique name for the pattern based off suggested name
            #   in the spec
            rootName = quilt_data.pat_spec_tryget(patternSpec, name=True)
            if rootName is None:
                rootName = "pattern"
            patternName = rootName
            i = 1

            with self.lock:
                while patternName in self._patterns.keys():
                    patternName = '_'.join([rootName, str(i)])
                    i += 1

                # store pattern spec in the member data
                quilt_data.pat_spec_set(patternSpec, name=patternName)
                quilt_data.pat_specs_add(self._patterns, patternSpec)


            # return the unique name for the pattern
            return patternName

        except Exception, e:
            logging.exception(e)
            raise


    def Query(self, submitterNameKey, querySpec):
        """
        string Query(                       # return the ID of the query
            string submitterNameKey         # key that the submitter received
                                            #   when it was registered with this
                                            #   master
            dict querySpec                  # the details of the query
                                            #   necessary from the user
        )
        """


        # qid must be set because we use it when reporting the error
        if submitterNameKey is not None:
            qid = str(submitterNameKey) + " unnamed query"
        else:
            qid = "Unknown query"

        # try the following 
        try:

            # a slightly better name for the query id
            tqid = quilt_data.query_spec_tryget(querySpec, name=True)
            if tqid is not None:
                qid = tqid

            # placeholder query spec to reserve the unique qid
            tmpQuerySpec = querySpec.copy()

            # get pattern name from the query spec
            patternName = quilt_data.query_spec_get(
                querySpec, patternName=True)

            # acquire lock
            with self.lock:
                # copy the patternSpec the query references
                patternSpec = quilt_data.pat_specs_get(
                    self._patterns, patternName).copy()
                # generate a query id
                baseqid = submitterNameKey + "_" + patternName
                i = 0
                qid = baseqid
                while qid in self._queries or qid in self._history:
                    i += 1
                    qid = baseqid + "_" + str(i)

                # store querySpec in Q to reserve query id
                quilt_data.query_spec_set(tmpQuerySpec, name=qid)
                quilt_data.query_specs_add(self._queries, tmpQuerySpec)

            # this the query spec we will be manipulating, give it the id
            # that we generate, we will eventually replace the placeholder
            # in the member q
            quilt_data.query_spec_set(querySpec, name=qid)

            code = quilt_data.pat_spec_tryget(
                patternSpec, code=True)

            # using the set of sources described in the query code if
            #   they exist, or the ones described by mappings otherwise
            # group variable mapping's by target source and source pattern
            #   store in local collection, 
            #   map{source:
            #       map{sourcePattern:
            #           map{sourcePatternInstance:
            #               map{srcVar:Var}}}}

            #   store in local collection.  We later want to iterate the
            #   source mangers efficiently, so we pre process a varDict here
            #   which provides a direct mapping from srcVariables to 
            #   queryVariables, grouped by sources and patterns and pattern 
            #   instances

            # if pattern code specified
            #   parse the pattern text, and get set of variables mentioned
            #   in the pattern code
            if code is not None:
                # pattern code should be generated to account for any variables
                #   that will need to be substituted with default value to
                #   make the code syntactically correct
                code = quilt_data.generate_query_code(patternSpec,None)
                # get the variables mentioned in the pattern code
                varDict = quilt_parse.get_pattern_src_refs(code)
                append = False
            else:
                varDict = var_dict.create()
                append = True

            patVarSpecs = quilt_data.pat_spec_tryget(
                patternSpec, variables=True)

            mappings = quilt_data.pat_spec_tryget(
                patternSpec, mappings=True)


            #logging.info("got patVarSpecs: " + str(patVarSpecs))
            #logging.info("got mappings: " + str(mappings))
            # if code was specified, only bother making the map for
            #   sources referenced in the code, otherwise use anything
            #   that was declared in the pattern spec mappings 
            if patVarSpecs is not None and mappings is not None:

                patVars = patVarSpecs.keys()

                # logging.debug("Iterating variables: " + str(patVars))

                for m in mappings:
                    varName = quilt_data.src_var_mapping_spec_get(
                        m, name=True)
                    if varName not in patVars:
                        continue

                    src = quilt_data.src_var_mapping_spec_get(
                        m, sourceName=True)
                    pat = quilt_data.src_var_mapping_spec_get(
                        m, sourcePattern=True)
                    var = quilt_data.src_var_mapping_spec_get(
                        m, sourceVariable=True)
                    ins = quilt_data.src_var_mapping_spec_tryget(
                        m, sourcePatternInstance=True)

                    logging.debug("considering: varDict[" + var + "] = " +
                                  str(varName))
                    # set append to appropriate value so that the varDict does
                    # not grow from mappings alone
                    var_dict.set_var(varDict, src, pat, ins, var, varName,
                        append=append)

            else:
                logging.info("No query variables were specified")

            logging.info("got varDict:\n " + pprint.pformat(varDict))

            varSpecs = quilt_data.query_spec_tryget(
                querySpec, variables=True)


            # initialize list of srcQueries
            srcQuerySpecs = None

            # iterate the collection of sources, and build collection of 
            # srcQuerySpecs for each source
            for source in varDict.keys():

                # use variable mapping's source name to get proxy to 
                #   that source manager
                with get_client_proxy_from_type_and_name(
                        self, "smd", source) as srcMgr:

                    patterns = srcMgr.GetSourcePatterns()

                    # iterate the collection of sourcePatterns for current 
                    #   source
                    for patternName in patterns:
                        # NOTE we could have decided to build a temp map
                        # of all patterns and close the source manager 
                        # connection sooner, but it will have no practical
                        # effect to keep the source manager connection a
                        # might longer while doing the below processing

                        # skip the creation of source queries for source 
                        #   patterns not references in the query
                        if patternName not in varDict[source]:
                            continue

                        # get the sourcePatternSpec from the proxy 
                        srcPatSpec = srcMgr.GetSourcePattern(patternName)

                        # create a query spec objects
                        curSrcQuerySpecs = create_src_query_specs(
                            srcPatSpec, varDict, varSpecs, patVarSpecs,
                            qid, source, patternName)

                        for srcQuerySpec in curSrcQuerySpecs.values():
                            # append completed sourceQuerySpec to querySpec
                            srcQuerySpecs = quilt_data.src_query_specs_add(
                                srcQuerySpecs, srcQuerySpec)


            # store sourceQueries in the querySpec
            if srcQuerySpecs is not None:
                quilt_data.query_spec_set(querySpec,
                    sourceQuerySpecs=srcQuerySpecs)

            # use querySpec and srcQuery list
            # to create a validation string                    
            msg = {'Query to run': querySpec,
                   'Sources to be queried': varDict.keys()}

            validStr = pprint.pformat(msg)


            # ask submitter to validate the source Queries
            # get_client function is threadsafe, returns with the lock off
            with get_client_proxy_from_type_and_name(
                    self, "qsub", submitterNameKey) as submitter:

                # call back to the submitter to get validation
                validated = submitter.ValidateQuery(validStr, qid)

            # if submitter refuses to validate, 
            if not validated:
                logging.info("Submitter: " + submitterNameKey +
                             " did not validate the query: " + qid)
                # acquire lock remove query id from q
                # delete the query record, it was determined invalid
                # return early
                with self.lock:
                    quilt_data.query_specs_del(self._queries, qid)
                return

            logging.info("Submitter: " + submitterNameKey +
                         "did validate the query: " + qid)

            # acquire lock
            with self.lock:
                # store querySpec state as INITIALIZED, and place 
                # validated contents in member data
                quilt_data.query_spec_set(querySpec,
                    state=quilt_data.STATE_INITIALIZED)
                quilt_data.query_specs_add(self._queries,
                    querySpec)

            # Process query...
            # get the path to the current directory
            # formulate the command line for quilt_query
            queryCmd = [
                os.path.join(os.path.dirname(__file__), "quilt_query.py"),
                qid]
            if self._args.log_level is not None:
                queryCmd.append("--log-level")
                queryCmd.append(self._args.log_level)

            if self._args.log_file is not None:
                queryCmd.append("--log-file")
                queryCmd.append(self._args.log_file)

                # use subprocess module to fork off the process
                # script, pass the query ID
            #           sei_core.run_process("sleep 5 && " + ' '.join(queryCmd) + " &",shell=True)
            subprocess.Popen(queryCmd)

        # catch exception! 
        except Exception, error:

            logging.exception(error)

            try:
                # submit launched this call asynchronously and must be made
                # aware of the unexpected error
                # call submit's OnSubmitProblem
                logging.info("Attempting to get proxy for error report")
                with get_client_proxy_from_type_and_name(
                        self, "qsub", submitterNameKey) as submitter:
                    logging.info("Attempting to send error to submitter")
                    Pyro4.async(submitter).OnSubmitProblem(qid, error)

            except Exception, error2:
                # stuff is going horribly wrong, we couldn't notify submitter
                logging.error("Unable to notify submitter: " +
                              str(submitterNameKey) +
                              " of error when submitting query: " + str(qid))
                logging.exception(error2)

            try:
                logging.info("Cleaning up after query error")
                if self.lock.locked():
                    self._try_move_query_to_hist(
                        qid, quilt_data.STATE_ERROR)
                else:
                    with self.lock:
                        self._try_move_query_to_hist(
                            qid, quilt_data.STATE_ERROR)
            except Exception, error2:
                logging.error("Failed to move error'd query to history")
                logging.exception(error2)


    def GetQueryQueueStats(self):
        """
        format a string with information about all the Query's in the q   
        """
        with self.lock:
            return pprint.pformat(self._queries.keys())

    def TryGetQueryStats(self, queryId):
        """
        format a string with information about the specified query
        return None if not found
        """

        with self.lock:
            if queryId not in self._queries:
                return None
            else:
                return pprint.pformat(self._queries[queryId])

    def GetQueryHistoryStats(self, queryId=None):
        """
        format a string with information about the specified query
        from the history, or provide stats for all if no queryId is 
        specified
        """
        try:
            results = None
            # acquire lock
            with self.lock:
            # if queryID specified
                if queryId is not None:
                    # throw error if query not found in history, 
                    # otherwise return the query's record
                    if queryId not in self._history:
                        raise Exception("query id: " + str(queryId) +
                                        " is not present in history")
                    results = pprint.pformat(quilt_data.query_specs_get(
                        self._history, queryId))
                else:
                    # return complete history summary
                    results = pprint.pformat(self._history.keys())

            return results

        except Exception, e:
            logging.exception(e)
            raise

    def GetPatternStats(self):
        """Return a string describing the patterns defined in the query
        master"""

        with self.lock:
            return pprint.pformat(self._patterns)

    def _try_move_query_to_hist(self, queryId, state):
        """Private function, only call with self_lock engaged"""
        querySpec = quilt_data.query_specs_trydel(self._queries, queryId)
        # else find queryId in history
        if querySpec is None:
            querySpec = quilt_data.query_specs_tryget(self._history,
                queryId)
        else:
            # move query spec from q to history member collection
            quilt_data.query_specs_add(self._history, querySpec)

        if querySpec is not None:
            # mark the query as the specified state
            quilt_data.query_spec_set(querySpec, state=state)

        return querySpec

    #REVIEW
    def AppendQueryResults(self, queryId, results):
        """
        Append the specified eventList to the specified queryId
        """
        try:
            # acquire lock
            with self.lock:
                # Get query from Q
                querySpec = quilt_data.query_specs_get(self._queries, queryId)
                # Try to get any existing results then
                #   append the results into the query spec

                # set the results into the query spec
                existingEvents = quilt_data.query_spec_tryget(
                    querySpec, results=True)

                if existingEvents is None:
                    existingEvents = []

                # append the results into the query spec
                quilt_data.query_spec_set(querySpec,
                    results=(existingEvents + results))

        except Exception, error:
            try:
                # log exception here, because there is no detail in it once we 
                #   pass it across pyro
                logging.error("Unable append results for query: " +
                              str(queryId))
                logging.exception(error)
            finally:
                # throw the exception back over to the calling process
                raise error

    def OnQueryError(self, qid, error):
        """Called when an asynchronous query produces an exception"""

        try:
            # remove query from q and place in history with error state
            # multiple source errors can trigger this, so it is reasonable to 
            # expect multiple calls
            with self.lock:
                # mark the query as completed in state
                self._try_move_query_to_hist(
                    qid, quilt_data.STATE_ERROR)

        except Exception, e:
            logging.error("Unable to properly process query error")
            logging.exception(e)
            raise

        finally:
            # log the execution
            logging.error("Error occurred when processing query: " + str(qid))
            logging.error(quilt_core.exception_to_string(error))

    def BeginQuery(self, queryId):
        """
        string queryID          # the query we are interested in
        
        Called by quilt_query to Move a query into the an active state,
        and return a copy of the query
        """

        try:
            logging.info("Beginning query: " + str(queryId))
            patternSpec = None

            # lock self
            with self.lock:

                # get the query from the Q
                # if can't get it raise exception
                querySpec = quilt_data.query_specs_get(self._queries, queryId)

                queryState = quilt_data.query_spec_get(querySpec, state=True)
                # if query state is not expected INITIALIZED state
                if queryState != quilt_data.STATE_INITIALIZED:
                    # raise exception
                    raise Exception("Query: " + str(queryId) +
                                    " is not ready for processing")

                # move query to ACTIVE state
                quilt_data.query_spec_set(querySpec,
                    state=quilt_data.STATE_ACTIVE)

                # create a  copy of the query
                querySpec = querySpec.copy()

                # get a copy of the patternSpec
                patternSpec = quilt_data.pat_specs_get(self._patterns,
                    quilt_data.query_spec_get(querySpec, patternName=True))
                patternSpec = patternSpec.copy()

            # returning copy because we don't want to stay locked when asking
            #   pyro to marshall across process bounds.  Not that I know for
            #   a fact that that won't work, but it sounds like a bad idea
            # return the pattern and query spec 
            return patternSpec, querySpec

        except Exception, error:
            try:
                # log exception here, because there is no detail in it once we 
                #   pass it across pyro
                logging.error("Unable begin query: " + str(queryId))
                logging.exception(error)
            finally:
                # throw the exception back over to the calling process
                raise error

    def CompleteQuery(self, queryId):
        """
        Called by quilt_query upon completion of all source queries
        """

        try:
            # lock self
            with self.lock:
                # delete the query from the Q
                # set the state to COMPLETED
                # Add the query to the history
                self._try_move_query_to_hist(queryId,
                    quilt_data.STATE_COMPLETED)
        except Exception, error:
            try:
                # log exception here, because there is no detail in it once we 
                #   pass it across pyro
                logging.error("Unable complete query: " + str(queryId))
                logging.exception(error)
            finally:
                # throw the exception back over to the calling process
                raise error


def get_client_proxy(clientRec):
    """
    return a pyro proxy object to the specified by the client record
    """
    pyroname = clientRec["clientName"]
    nshost = clientRec["registrarHost"]
    nsport = clientRec["registrarPort"]

    uri = quilt_core.get_uri(nshost, nsport, pyroname)

    return Pyro4.Proxy(uri)


def get_client_proxy_from_type_and_name(qm, clientType, clientName):
    # lock access to the clients of the query master
    with qm.lock:
        rec = qm.clients[clientType][clientName].copy()
    return get_client_proxy(rec)


def create_src_query_specs(
        srcPatSpec, varDict, varSpecs, patVarSpecs, qid, source, patternName):
    """
    get new sourceQuery specs from the sourcePatternSpec and the
    varDict
    """

    srcQuerySpecs = None

    patInstanceDict = varDict[source][patternName]

    for patInstanceName in patInstanceDict.keys():
        curSrcQuerySpec = create_src_query_spec(
            srcPatSpec, patInstanceName, varSpecs, patVarSpecs, qid, source,
            patternName, varDict)

        srcQuerySpecs = quilt_data.src_query_specs_add(srcQuerySpecs,
            curSrcQuerySpec)

    return srcQuerySpecs


def create_src_query_spec(
        srcPatSpec, srcPatInstance, varSpecs, patVarSpecs, qid, source,
        patternName,
        varDict):
    """Helper function for filling out a srcQuerySpec with variable values"""

    srcPatVars = quilt_data.src_pat_spec_get(
        srcPatSpec, variables=True)
    if srcPatVars is None:
        return

    srcVarToVarDict = varDict[source][patternName][srcPatInstance]

    logging.debug("srcVarToVarDict: " + str(srcVarToVarDict))
    logging.debug("varDict is " + str(varDict))

    srcQueryVarSpecs = None
    # iterate the variables in the "new" 
    #   sourceQuerySpec
    for srcVarName, srcPatVarSpec in srcPatVars.items():

        # find that source variable in the pattern's 
        #   mappings
        # get the name of the query variable that maps to it
        varValue = None
        if srcVarName in srcVarToVarDict:
            varName = srcVarToVarDict[srcVarName]

            # get the value of the query variable from the
            #   querySpec, if it was given in the query spec
            varSpec = quilt_data.var_specs_tryget(varSpecs, varName)
            if varSpec is not None:
                varValue = quilt_data.var_spec_tryget(varSpec, value=True)

            if (varValue is None and patVarSpecs is not None
            and varName in patVarSpecs):
                # user did not supply value for the variable in the
                # query, but there is a default set in pattern definition
                patVarSpec = quilt_data.var_specs_tryget(
                    patVarSpecs, varName)
                # use the default in the pattern
                varValue = quilt_data.var_spec_tryget(
                    patVarSpec, default=True)

        if varValue is None:
            # pattern definer did not supply a default, check
            # to see if there is a default in the source pattern
            varValue = quilt_data.var_spec_tryget(
                srcPatVarSpec, default=True)

            if varValue is None:
                # could not determine a value for this variable
                # must throw error
                raise Exception("""No value set or default found
                    for the variable: """ + srcVarName)

        # create a source query variable value with the determined value
        srcQueryVarSpec = quilt_data.var_spec_create(
            name=srcVarName, value=varValue)
        # append it to a list of src query variables
        srcQueryVarSpecs = quilt_data.var_specs_add(
            srcQueryVarSpecs, srcQueryVarSpec)

    # Combine strings to get a name for this source query
    srcQueryName = '_'.join([qid, source, patternName])
    if srcPatInstance is not None:
        srcQueryName += "_" + str(srcPatInstance)

    # create and return a src query spec
    # TODO see Issue I001, this name may not be unique
    # logging.info("srcPatSpec looks like: " + str(srcPatSpec))
    srcPatName = quilt_data.src_pat_spec_get(srcPatSpec, name=True)

    # get whether src pattern is ordered 
    ordered = quilt_data.src_pat_spec_get(srcPatSpec, ordered=True)

    logging.debug("Creating " + srcQueryName + " from " + srcPatName)
    return quilt_data.src_query_spec_create(
        name=srcQueryName,
        srcPatternName=srcPatName,
        srcPatternInstance=srcPatInstance,
        source=source,
        ordered=ordered,
        variables=srcQueryVarSpecs)


                            

