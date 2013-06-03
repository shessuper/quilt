#!/usr/bin/env python
import logging
import threading
import quilt_data
import itertools

class _field:
    def __init__(self, eventsId, fieldName):
        # set id and field name in member data
        self.eventsId = eventsId
        self.fieldName = fieldName

    def __getitem__(self, index): 
        # get the event list from the global event dict with this id
        eventSpecs = _get_events(self.eventsId)
        eventSpec = eventSpecs[index]
        return eventSpec[self.fieldName]

    def __setitem__(self,key,val):
        # raise unimplemented exception
        raise Exception("This function is not implemented")

    def __delitem__(self, key):
        # raise unimplemented exception
        raise Exception("This function is not implemented")

    def __len__(self):
        # get the event list from the global event dict with this id
        # return length of event list
        eventSpecs = _get_events(self.eventsId)
        return len(eventSpecs)
        
    def __eq__(self, value):
        # construct a new eventID based on the calling context
        # NOTE, we assume RHS is a literal currently
        returnEventsId = (self.eventsId + "." + self.fieldName + 
                "==" + str(value))

        # if if eventID exist in global event dict
        if _has_events(returnEventsId):
            # return those events
            return _pattern(returnEventsId)

        # get the event list from the global event dict with this id
        events = _get_events(self.eventsId)


        # create new event list with events that have this
        #   field matching the value
        returnEvents = [e for e in events if e[self.fieldName] == value]

        # set new event list into global events dict
        # return a new _pattern for the new event list
        return _pattern(returnEventsId, returnEvents)


class _pattern:
    def __init__(self, eventsId, events = None):
        # set events and id in member data
        self.eventsId = eventsId
        # if a new list of events is input, store them in
        #   the global pool
        if events != None:
            _set_events(eventsId,events)

        if not _has_events(eventsId):
            raise Exception("No event list available for: " + str(eventsId))

    def __getitem__(self, fieldName):
        # return a new _field object from this
        #   eventId, and fieldName
        return _field(self.eventsId, fieldName)
        
    def __setitem__(self,key,val):
        # raise unimplemented exception
        raise Exception("This function is not implemented")

    def __delitem__(self, key):
        # raise unimplemented exception
        raise Exception("This function is not implemented")

    def __len__(self):
        # get the event list from the global event dict with this id
        # return length of event list
        return len(_get_events(self.eventsId))

def at(pattern):
    # return timestamp field of the pattern
    return pattern['timestamp']

def source(srcName,srcPatName,srcPatInstance=None):
    """
    Construct a pattern wrapper from the specified source
    """
    # use the global query spec
    srcQuerySpecs = quilt_data.query_spec_get(_get_query_spec(), 
            sourceQuerySpecs=True)
    # logging.debug("srcQuerySpecs:\n" + pprint.pformat(srcQuerySpecs))

    # logging.debug("Looking for Source: " + str(srcName) + ", pattern: " + str(srcPatName) 
    #         + ". instance: " + str(srcPatInstance) )


    # iterate the srcQueries
    for srcQueryId, srcQuerySpec in srcQuerySpecs.items():
        # if matching (srcName, patName, and patInstanceName)
        # if None was supplied as one of the parameter, then there
        #   must only be one instance to choose, keyed by 'None'
        curSrc = quilt_data.src_query_spec_get(srcQuerySpec, 
                source=True) 
        curSrcPat = quilt_data.src_query_spec_get( srcQuerySpec, 
                srcPatternName=True) 
        curSrcPatInst = quilt_data.src_query_spec_tryget(
                    srcQuerySpec, srcPatternInstance=True) 

        # logging.debug("checking " + curSrc + ", " + curSrcPat + 
        #         ", " + str( curSrcPatInst))

        if (srcName == curSrc and 
            srcPatName == curSrcPat and 
            srcPatInstance == curSrcPatInst):

            # get the global srcResults for that srcQueryID
            srcResults = _get_events(srcQueryId)

            # return a new _pattern with the srcResults as the events
            return _pattern(srcQueryId, srcResults)

    # raise exception if mathing srcQuery not found
    raise Exception("Source: " + str(srcName) + ", pattern: " + str(srcPatName) 
            + ". instance: " + str(srcPatInstance) +  
            ", could not be found among the source queries")


# http://stackoverflow.com/questions/3844801/check-if-all-elements-in-a-list-are-identical
def _check_equal(iterator):
    try:
        iterator = iter(iterator)
        first = next(iterator)
        return all(first == rest for rest in iterator)
    except StopIteration:
        return True

def concurrent(*patterns):
    """return all patterns that occur at the same time"""

    # generate name based on execution context
    returnEventsId = "concurrent("
    for curPattern in patterns:
        returnEventsId += curPattern.eventsId + ","
    returnEventsId[-1] = ')'

    # if eventlist of generated name exists
    if _has_events(returnEventsId):
        #   return previously generated event list
        return _pattern(returnEventsId)

    # construct a new empty list of fields
    # itterate the patterns
        # call 'at' on the pattern, append to list of fields
    fields = [at(curPattern) for curPattern in patterns]

    # join all of the field lists using an equality test
    joined = itertools.ifilter(_check_equal, itertools.product(*fields))

    # generate new event list only containing events with timestamps
    #   found during the join
    returnEvents = []
    for curPattern in patterns:
        curEvents = _get_events(curPattern.eventsId)
        for curEvent in curEvents:
            if at(curEvent) in joined:
                returnEvents.append(curEvent)

    # record new event list in event dict with this name
    # by returning a _pattern for the new list
    return _pattern(returnEventsId, returnEvents)

    

def _get_events(eventsId):
    logging.debug("accessing " + str(eventsId))
    return globals()['_eventPool'][eventsId]

def _set_events(eventsId,events):
    globals()['_eventPool'][eventsId] = events

def _has_events(eventsId):
    # logging.debug("Looking for " + str(eventsId) + " in " + str(globals()['_eventPool'].keys()))
    return eventsId in globals()['_eventPool']

def _get_query_spec():
    return globals()['_querySpec']

_interpret_lock = threading.Lock()

def evaluate_query(patternSpec, querySpec, srcResults):
    """
    Semantically process the source results according to the pattern
    code.  Return the results.
    NOTE: This funciton is non rentrant.
        Do not call evaluate_query when this is on the callstack
    NOTE: The srcResults collection may be modified after calling
    """
    # try to evaluate the query
    with _interpret_lock:
        try:
            # set querySpec and srcResults (as eventDict) into global scope
            globals()['_querySpec'] = querySpec
            # we will be adding things to the event pool, this will modify
            # a colleciton that is named only to have source results, so we
            # preform a rename here.  The calling context will not use it
            # anyway. See NOTE in docstring
            # TODO, figure out if a .copy() would do a deep copy, or think
            #   manual shallow 
            globals()['_eventPool'] = srcResults

            # evaluate the pattern code
            code = quilt_data.pat_spec_get(patternSpec, code=True)

            retpattern = eval(code)

            retobj = _get_events(retpattern.eventsId)

            # logging.debug ("Rsults of interpret are:\n" + 
            # str(type(retobj)) + "\n" + str(dir(retobj)) +"\n" + 
            # pprint.pformat(retobj))

            # return results
            return retobj

        finally:
            # remove querySpec and eventDict from globals scope
            if '_eventPool' in globals():
                del globals()['_eventPool']
            if '_querySpec' in globals():
                del globals()['_querySpec']