#!/usr/bin/env python

#******************************************************************************
# Copyright (c) 2016, The Regents of the University of California (Regents).
# All Rights Reserved. See LICENSE for license details.
#------------------------------------------------------------------------------
#------------------------------------------------------------------------------
# O3-Pipeview Visualization Helper
#------------------------------------------------------------------------------
#------------------------------------------------------------------------------
#
# Christopher Celio
# 2016 Mar 18
#
# INPUT: a *.out file generated by a Rocket-chip simulator (e.g., BOOM). Each
# output line is annotated with the fetch sequence number to help correlate
# which instruction corresponds to which timestamp printouts:
#
#   (###; O3PipeView:stage: <timestamp-count>)
#
# OUTPUT: a trace compatible with the gem5 o3-pipeview.py visualization script.
#
# Helper script that processes *.out files from a processor (e.g., RISC-V BOOM),
# and re-constructs the log file to match the format expected by the Gem5
# o3-pipeview.py tool.
#
# The theory is that the processor assigns a fetch-sequence number to each
# instruction. As the instruction travels down the pipeline (potentially
# out-of-order), each stage prints to the *.out log the fetch-sequence number
# and the time-stamp. The resulting *.out log will contain an interleaving of
# committed and misspeculated instructions writing time stamps.

# The o3-pipeview.py tool expects to see each instruction's time stamps printed
# contigiously.

# TODO:
#   implement lists as hash tables
#   verify there's no key collision once using hash tables

import optparse

from collections import deque

def getFSeqNum(line, idx):
    return int(line[0:idx])

# remove the fseq number and print the line
def writeOutput(line, idx):
    print line[idx+2:],

# re-create the proper output from the retire message and
# the store-comp message
def writeRetireStoreOutput(ret_line, st_line, r_id, idx, s_idx):
    s_id = getFSeqNum(st_line, idx)
    if r_id != s_id:
        print "FAILURE:"
        print ret_line
        print st_line
    assert r_id == s_id, "wrong store entry!"
    s_tsc = st_line[s_idx+1:]
    end_idx = ret_line.rfind(':')
    print ret_line[idx+2:end_idx+1], s_tsc,

# return True if the event was found
# otherwise return False (the instruction was misspeculated)
def findAndPrintEvent(target_id, lst, stage_str, idx):
    for i in range(len(lst)):
        temp_id = getFSeqNum(lst[i], idx)
        if temp_id == target_id:
            writeOutput(lst.pop(i), idx)
            return True
    print "O3PipeView:", stage_str,": 0"
    return False

def isStore(line):
    if "sw " in line or \
       "sd " in line or \
       "sh " in line or \
       "sb " in line or \
       "amo" in line:
        return True
    else:
        return False


def generate_pipeview_file(log):
    lines = log.readlines()

    # find fetch sequence number separator, and cache result
    idx = lines[0].find(';')
    assert (idx != -1), "Couldn't find fseq number. Has the file been properly generated?"

    # in-order stages get to use queues
    q_if  = deque()
    q_dec = deque()
    # out-of-order stages must use lists
    l_iss = []
    l_wb  = []


    # run over the entire list once to get the store completions,
    # as they occur after the store retires and thus don't fit neatly
    # into our for loop below
    l_stc = [line for line in lines if "store-comp" in line]
    # cache the s_idx value
    s_idx = l_stc[0].find(':')

    for line in lines:
        if "fetch" in line:
            q_if.append(line)
        elif "decode" in line:
            q_dec.append(line)
        elif "issue" in line:
            l_iss.append(line)
        elif "complete" in line:
            l_wb.append(line)
        elif "retire" in line:
            r_id = getFSeqNum(line, idx)
            while q_if:
                fetch_id = getFSeqNum(q_if[0], idx)
                if fetch_id > r_id:
                    break
                elif fetch_id == r_id:
                    # print out this instruction's stages and retire it
                    # (they'll be the head of all of the in-order queues)
                    fetch = q_if.popleft()
                    writeOutput(fetch, idx)
                    writeOutput(q_dec.popleft(), idx)
                    print "O3PipeView:rename: 0"
                    print "O3PipeView:dispatch: 0"
                    findAndPrintEvent(fetch_id, l_iss, "issue", idx)
                    findAndPrintEvent(fetch_id, l_wb, "complete", idx)
                    if isStore(fetch):
                        writeRetireStoreOutput(line, l_stc.pop(0), r_id, idx, s_idx)
                    else:
                        writeOutput(line, idx)
                    break
                else:
                    # print out misspeculated instruction
                    writeOutput(q_if.popleft(), idx)
                    if q_dec and fetch_id == getFSeqNum(q_dec[0], idx):
                        writeOutput(q_dec.popleft(), idx)
                        print "O3PipeView:rename: 0"
                        print "O3PipeView:dispatch: 0"
                        findAndPrintEvent(fetch_id, l_iss, "issue", idx)
                        findAndPrintEvent(fetch_id, l_wb, "complete", idx)
                    else:
                        print "O3PipeView:decode: 0"
                        print "O3PipeView:rename: 0"
                        print "O3PipeView:dispatch: 0"
                        assert not findAndPrintEvent(fetch_id, l_iss, "issue", idx), \
                            "Found issue time stamp with no corresponding decode"
                        assert not findAndPrintEvent(fetch_id, l_wb, "complete", idx), \
                            "Found time stamp with no corresponding decode"
                    print "O3PipeView:retire: 0:store: 0"


def main():
    parser = optparse.OptionParser()
    parser.add_option('-f','--file', dest='infile',
        help='The input *.out file to parse.', default="")

    (options, args) = parser.parse_args()

    assert options.infile != "", "Empty input file!"

    with open(options.infile, 'r') as log:
        generate_pipeview_file(log)


if __name__ == '__main__':
    main()
