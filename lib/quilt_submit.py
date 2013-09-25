#!/usr/bin/env python
# Copyright 2013 Carnegie Mellon University 
#  
# This material is based upon work funded and supported by the Department of Defense under Contract No. FA8721-
# 05-C-0003 with Carnegie Mellon University for the operation of the Software Engineering Institute, a federally 
# funded research and development center. 
#  
# Any opinions, findings and conclusions or recommendations expressed in this material are those of the author(s) and 
# do not necessarily reflect the views of the United States Department of Defense. 
#  
# NO WARRANTY. THIS CARNEGIE MELLON UNIVERSITY AND SOFTWARE ENGINEERING INSTITUTE 
# MATERIAL IS FURNISHEDON AN "AS-IS" BASIS. CARNEGIE MELLON UNIVERSITY MAKES NO 
# WARRANTIES OF ANY KIND, EITHER EXPRESSED OR IMPLIED, AS TO ANY MATTER INCLUDING, 
# BUT NOT LIMITED TO, WARRANTY OF FITNESS FOR PURPOSE OR MERCHANTABILITY, 
# EXCLUSIVITY, OR RESULTS OBTAINED FROM USE OF THE MATERIAL. CARNEGIE MELLON 
# UNIVERSITY DOES NOT MAKE ANY WARRANTY OF ANY KIND WITH RESPECT TO FREEDOM FROM 
# PATENT, TRADEMARK, OR COPYRIGHT INFRINGEMENT. 
#  
# This material has been approved for public release and unlimited distribution except as restricted below. 
#  
# Internal use:* Permission to reproduce this material and to prepare derivative works from this material for internal 
# use is granted, provided the copyright and "No Warranty" statements are included with all reproductions and 
# derivative works. 
#  
# External use:* This material may be reproduced in its entirety, without modification, and freely distributed in 
# written or electronic form without requesting formal permission. Permission is required for any other external and/or 
# commercial use. Requests for permission should be directed to the Software Engineering Institute at 
# permission@sei.cmu.edu. 
#  
# * These restrictions do not apply to U.S. government entities. 
#  
# Carnegie Mellon(r), CERT(r) and CERT Coordination Center(r) are registered marks of Carnegie Mellon University. 
#  
# DM-0000632 
import sys
import logging
import quilt_core
import Pyro4
import quilt_data
import pprint


class QuiltSubmit(quilt_core.QueryMasterClient):
    """
    Submit a query to the query master.  Hang around and wait to post a
    validation to the user if desired.  User can then abort the submission
    then exit
    """

    #   """
    #   the event loop control variable, if false event loop will
    #   not run, or stop running.  This variable is shared between threads
    #   and should not be accessed without a lock
    #   """
    _processEvents = True

    def __init__(self, args):
        # chain to call super class constructor 
        # super(QuiltSubmit, self).__init__(GetType())
        quilt_core.QueryMasterClient.__init__(self, self.GetType())
        self._args = args

    def ValidateQuery(self, queryMetricMsg, queryId):
        """
        string queryMetricMsg    message to user about time and space
                                 requirements for the generated query
        string queryID           the ID that the query master assigned to
                                 the query
        """
        try:
            print "Query ID is:", queryId

            logging.info("Receiving validation request for query: " +
                         str(queryId))

            if not self._args.confirm_query:
                print queryMetricMsg
                while True:
                    print "Would you like to confirm query? [y,n]: "
                    c = sys.stdin.readline()
                    if len(c) >= 1:
                        c = c[0]
                        if c == 'n' or c == 'N':
                            return False
                        if c == 'y' or c == 'Y':
                            break

            return True
        finally:
            # set process events flag to false end event loop, allowing
            # submitter to exit
            self.SetProcesssEvents(False)


    def OnRegisterEnd(self):
        """After registration is complete submit the query to the 
        query master"""
        # create a partial query spec dictionary
        #   set pattern name from args
        #   set notification address in spec
        #   set state as UNINITIALIZED
        querySpec = quilt_data.query_spec_create(
            name='new ' + self._args.pattern,
            state=quilt_data.STATE_UNINITIALIZED,
            patternName=self._args.pattern,
            notificationEmail=self._args.notification_email)

        #   set variables/values from args
        if self._args.variable is not None and len(self._args.variable) > 0:
            variables = quilt_data.var_specs_create()
            for v in self._args.variable:
                vname = v[0]
                vval = v[1]
                quilt_data.var_specs_add(variables,
                    quilt_data.var_spec_create(name=vname, value=vval))
            quilt_data.query_spec_set(querySpec, variables=variables)

        logging.info('Submitting query: ' + pprint.pformat(querySpec))

        # call remote method asynchronously, this will return right away
        with self.GetQueryMasterProxy() as qm:
            Pyro4.async(qm).Query(self._remotename, querySpec)

        logging.info('Query Submitted')

        # Validate query will be remote called from query master

        # return True to allow event loop to start running, which
        # should soon receive a validation callback from query master
        return True

    def GetType(self):
        return "qsub"


    def SetProcesssEvents(self, value):
        """
        value : boolean to set (in thread safe way) that tells this client
                whether it can stop processing events
        """
        if not value:
            logging.debug("soon will no longer process events")
        with self._lock:
            # set _processEvents to the specified value
            self._processEvents = value

    def OnEventLoopBegin(self):
        """
        void OnEventLoopBegin()
            lock the class lock
            read and return value of _processEvents
        """

        with self._lock:
            return self._processEvents

    def OnEventLoopEnd(self):
        """
        void OnEventLoopBegin()
            lock the class lock
            read and return value of _processEvents
        """
        with self._lock:
            return self._processEvents

    def OnSubmitProblem(self, queryId, exception):
        """Receive a message from the query master about a problem with
        the query submission"""

        try:
            # print out the query id and the message
            logging.error("Query submission error for: " + str(queryId) +
                          " : " + quilt_core.exception_to_string(exception))

            # I guess exception's don't keep their stacktrace over the pyro boundary
            #            logging.exception(exception)

        finally:
            # set process events flag to false end event loop, allowing
            # submitter to exit
            self.SetProcesssEvents(False)


def main(argv):
    # setup command line interface
    parser = quilt_core.main_helper('qsub',
        """
        Quilt Submit will allow submission of a query.  It will communicate
        with the query master, receive estimated time/space metrics of the
        query, get user confirmation (if no -y), then deliver the query, to
        the master for processing, print the query id, and then exit.
        A user may select a pattern and then substitute the VARIABLES
        defined in the pattern with the submitted values""",
        argv)

    parser.add_argument('pattern',
        help="name of the pattern to create the query from")
    parser.add_argument('-e', '--notification-email', nargs='?',
        help="comma separated list of emails to supply with notifications")
    parser.add_argument('-y', '--confirm-query', action='store_true',
        default=False, help="whether to automatically confirm the query")
    parser.add_argument('-v', '--variable', nargs=2, action='append',
        help="Arguments used to provide values to the variables in a pattern")

    # parse command line
    args = parser.parse_args(argv)

    # create the object and begin its life
    client = QuiltSubmit(args)

    # start the client
    quilt_core.query_master_client_main_helper({
        client.localname: client})


if __name__ == "__main__":
    main(sys.argv[1:])

