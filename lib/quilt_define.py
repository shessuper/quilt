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
import quilt_core
import quilt_data
import quilt_parse


class QuiltDefine(quilt_core.QueryMasterClient):
    def __init__(self, args):
        # chain to call super class constructor 
        quilt_core.QueryMasterClient.__init__(self, self.GetType())
        self._args = args

    def OnRegisterEnd(self):
        """Create a patternSpec dict from arguments (name, 
        VARIABLES, and VARIABLE to SOURCE_VARIABLE mappings), register
        this pattern with the query master"""

        # create the spec with it's requested name
        requestedName = self._args.name
        if requestedName is None:
            requestedName = "pattern"
        else:
            requestedName = self._args.name[0]

        patternSpec = quilt_data.pat_spec_create(name=requestedName)

        # create the specs for the variables
        variables = None
        if self._args.variable is not None:
            for v in self._args.variable:
                # create the variables section if it does not exist

                # first position of the cmd line argument is name of variable
                varName = v[0]
                varSpec = quilt_data.var_spec_create(name=varName)

                # if description was specified on cmd line, load it in the spec
                if len(v) > 1:
                    varDesc = v[1]
                    quilt_data.var_spec_set(varSpec, description=varDesc)

                # if default was specified on cmd line, load it in spec
                if len(v) > 2:
                    varDef = v[2]
                    quilt_data.var_spec_set(varSpec, default=varDef)
                variables = quilt_data.var_specs_add(variables, varSpec)

        quilt_data.pat_spec_set(patternSpec, variables=variables)

        mappings = None
        # create the specs for the variable mappings
        if self._args.mapping is not None:
            for m in self._args.mapping:
                varName = m[0]
                src = m[1]
                srcPat = m[2]
                srcVar = m[3]
                srcPatInstance = None
                if len(m) > 4:
                    srcPatInstance = m[4]



                # query variables are allowed to map to multiple
                # source variables.  Initialize a blank list if it isn't present
                # then append the new mapping information

                srcVarMappingSpec = quilt_data.src_var_mapping_spec_create(
                    name=varName,
                    sourceName=src,
                    sourcePattern=srcPat,
                    sourceVariable=srcVar,
                    sourcePatternInstance=srcPatInstance)

                mappings = quilt_data.src_var_mapping_specs_add(
                    mappings, srcVarMappingSpec)

        if mappings is not None:
            quilt_data.pat_spec_set(patternSpec, mappings=mappings)


        # if the pattern code is specified, set it in the pattern as
        #   a string
        if self._args.code is not None:
            # perform first pass parse on the pattern to ensure syntax
            # call get_pattern_vars from parser, but ignore the result
            #   this will check the syntax

            codestr = str(self._args.code)
            # store the code in the pattern
            quilt_data.pat_spec_set(patternSpec, code=codestr)

            # syntax parsing may be dependent on variables in the pattern, so
            #   generate the code str after replacing any pattern variables
            codestr = quilt_data.generate_query_code(patternSpec, None)
            quilt_parse.get_pattern_src_refs(codestr)


        # define patternSpec in the query master as a synchronous call
        # return will be the pattern name
        with self.GetQueryMasterProxy() as qm:
            patName = qm.DefinePattern(patternSpec)

        # print out pattern Name
        print 'Pattern', patName, ' defined'

        # return false (prevent event loop from beginning)

        return False

    def GetType(self):
        return "qdef"


def main(argv):
    # setup command line interface
    parser = quilt_core.main_helper('qdef', """
        Define a pattern to the query master.  A pattern is the template for a
        query.  The specified name of the pattern may be modified so as to
        become unique.  The official name of the pattern will be displayed.
        quilt_define will not return until pattern is defined or an error has
        occurred.  It will output the finalized (unique) name for the pattern
        """,
        argv)

    parser.add_argument('code', nargs='?',
        help="the code for the pattern")

    parser.add_argument('-n', '--name', nargs=1,
        help="suggested name of the pattern")

    parser.add_argument('-v', '--variable', nargs='+', action='append',
        help="""VARIABLE [DESCRIPTION [DEFAULT]]]  The variables that are
            part of the pattern, and an optional text description of the 
            purpose of the variable, and the optional default value of the
            variable""")

    parser.add_argument('-m', '--mapping', nargs='+', action='append',
        help="""VARIABLE SOURCE SOURCE_PATTERN SOURCE_VARIABLE
            [SOURCE_PATTERN_INSTANCE] Provide mapping from a pattern variable 
            to a source variable.  Pattern variables are described with the 
            -v, --variable command.  Source variables are described in the 
            data source manger's configuration files.  Source pattern
            instance is optional, but required if pattern is using the same 
            source pattern multiple times so the source variables can be 
            disambiguated""")

    args = parser.parse_args(argv)

    # create the object and begin its life
    client = QuiltDefine(args)

    # start the client
    quilt_core.query_master_client_main_helper({
        client.localname: client})


if __name__ == "__main__":
    main(sys.argv[1:])

