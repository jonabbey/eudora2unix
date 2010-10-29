#!/usr/bin/env python
"""Convert a Eudora .mbx (mbox) file to Linux/Unix mbox format.

See the master script 'Eudora2Unix.py' that calls this script for
all the mailboxes it loops over.

Usage:

   Eudora2Mbox.py [-a attachments_folder] [-t target_client] mailbox_file
   where target_client is either 'pine' or 'kmail'.

   Requires Python 2.2+

This program emits headers when an empty line is seen, in
accordance with RFC 2822.

En passant, DOS to Unix end-of-line conversion is applied, i.e.
a trailing carriage return (^M) on a line is removed.

Eudora uses a 'From ' line with a Eudora-specific substring '???@???'. 
Unix mbox format has the sender's e-mail here.  This script extracts 
the sender's e-mail from other mail headers and replaces that substring.

If a 'Date: ' is missing, it is added to make KMail happy and
extracted from the 'From ' line.

Altered by Stevan White 11/2001
* See
  <http://www.math.washington.edu/~chappa/pine/pine-info/misc/headers.html>
* Translated from Perl to Python, for no particularly compelling reason.
  Looks nicer, I think.  Probably a little more robust.
* Made to include info of whether message was read or not.
  To do this, made it read a parsed Eudora 'toc' file
  See collect_toc_info().
* Made to convey info that message was replied to.
  Eudora seems to do this by reading the whole mailbox searching for
  'In-Reply-To:' headers, then matching these with 'Message-ID:' headers.
  So we read through each message file twice.  See collect_replies().
* Made to do something sensible with Eudora's 'Attachment Converted' lines.

For more info on Internet mail headers, and the quasi-standard 'Status:'
header, see RFC 2076.
For more info on Pine's use of the 'X-Status:' header, look at its source, in
the file 'mailindx.c', in format_index_line(idata).
"""
__author__ = "Re-written in Python and extended by Stevan White <Stevan_White@hotmail.com>"
__date__ = "2003-04-29"
__version__ = "1.3"
__credits__ = """
	Based on Eudora2Unix.pl by Eric Maryniak <e.maryniak@pobox.com>;
	based in turn on eud2unx.pl by Blake Hannaford"""
import os
import re
import sys
import time
import string
import getopt
import urllib
from email import message
from email.mime.multipart import MIMEMultipart, MIMENonMultipart
from mailbox import mbox

import Header
import Message
import common

#
# Copyright and Author:
#
#     Copyright (C) 2002  Eric Maryniak
#
#     Eric Maryniak <e.maryniak@pobox.com>
#     WWW homepage: http://pobox.com/~e.maryniak/
#
# License:
#
#    This program is free software; you can redistribute it and/or modify
#    it under the terms of the GNU General Public License as published by
#    the Free Software Foundation; either version 2 of the License, or
#    (at your option) any later version.
#
#    This program is distributed in the hope that it will be useful,
#    but WITHOUT ANY WARRANTY; without even the implied warranty of
#    MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#    GNU General Public License for more details.
#
#    You should have received a copy of the GNU General Public License
#    along with this program; if not, write to the Free Software
#    Foundation, Inc., 59 Temple Place, Suite 330, Boston, MA  02111-1307  USA
#

if sys.hexversion < 33686000:
	sys.stderr.write( "Aborted: Python version must be at least 2.2.1" \
		+ os.linesep )
	sys.exit( 1 )

# Configuration.

# Add a 'X-Eudora2Unix: <ISO 8601 date> converted' header at the end
# of the emitted headers (see sub emit_headers),  0=no, 1=yes.
# This can come in handy later to differentiate between 'new' KMail
# messages and those inherited from the conversion.

emit_X_Eudora2Unix_Header = 1

# End of configuration.

# Program name and title in various banners.
P = sys.argv[0]

exit_code = 0	# exit code: 0 if all ok, 1 if any warnings or errors

line_no = 0	# line number of current line record (for messages)


re_attachment = re.compile( '^Attachment converted: (.*?)$', re.IGNORECASE )

def convert( mbx, opts = None ):
	"""
	Start at the Eudora specific pattern "^From ???@???" and keep gathering
	all headers.  When an empty line is found, emit the headers.

	Replace ???@??? with the e-mail address in "From: " (if found), or else
	use "Sender: " or else "Return-Path: " or else use the magic address
	"unknown@unknown.unknown" for later analysis (easily greppable).

	Also add a "Date: " if missing (mostly for outbound mail sent by
	yourself) which is extracted from the Eudora "From ???@??? ..." line,
	but is reformatted, because Eudora has the order in the datum items
	wrong.
	Eudora uses:
		dayname-abbr monthname-abbr monthnumber-nn time-hh:mm:ss
		year-yyyy
	whereas it should be:
		dayname-abbr monthnumber-nn monthname-abbr year-yyyy
		time-hh:mm:ss
	Example:
		Thu 03 Jan 2002 11:42:42    (24 characters)

	"""

	print "Converting %s", (mbx)

	global err, warn, log
	global line_no
	if not mbx:
		fatal( P + ': usage: Eudora2Mbox.py eudora-mailbox-file.mbx' )
		return 0

	attachments_dir = None
	target = ''
	if opts:
		for f, v in opts:
			if f == '-a':
				attachments_dir = v
			elif f == '-t':
				target = v

	common.msg_no	= 0	# number of messages in this mailbox
	common.line_no	= 0	# line number of current line record (for messages)

	headers = None
	last_file_position = 0
	msg_offset = 0

	re_initial_whitespace = re.compile( r'^[ \t]+(.*?)$' )

	log = Log( mbx )

	try:
		INPUT = open( mbx, 'r' )
	except IOError, ( errno, strerror ):
		INPUT = None
		return fatal( P + ': cannot open "' + mbx + '", ' + strerror )

	toc_info = TOC_Info( mbx )
	replies = Replies( INPUT )

	#
	# Main loop, that reads the mailbox file and converts.
	#
	# Sad issues with the nice python construct
	#	for line in INPUT:
	# It appears to read the whole file into an array before executing
	# the loop!  Besides being grotesquely inefficient, it blows up the
	# use of tell() within the loop.  See
	# <http://www.python.org/peps/pep-0234.html>
	while True:
		line = INPUT.readline()
		if not line:
			break
		line_no += 1

#		if line.find( 'From ', 0, headerblob_len ) == 0:

		# find returns -1 (i.e., true) if it couldn't find
		# 'Find ', so in fact this next if is looking to see
		# if the line does *not* begin with 'Find '

		if line.find( 'Find ', 0, 5 ) and re_message_start.match( line ):
			if headers:
				# Error
				#
				# We have a "From " line while already 
				# _in_ the headers. The previous message is 
				# probably empty and does not have the required
				# empty line to terminate the message
				# headers and start the message body.
				# Finally, emit this as a message
				#
				log.error( 'Message start found inside message',
					   common.msg_no, common.line_no )
				emit_headers( headers, toc_info,
					      msg_offset, common.msg_no, replies, OUTPUT )
			else:
				#
				# Bingo, we're in a message.
				#
				pass

			msg_offset = last_file_position
			headers = Header()
			headers.add( 'From ', line[5:].strip() )
			common.msg_no += 1
		else:
			if headers:
				if re_initial_whitespace.match( line ):
					# Header "folding" (RFC 2822 3.2.3)
					headers.appendToLast( line )
				elif len( line.strip() ) == 0: 
					# End of message headers.

					# here is where we could
					# create the message

					emit_headers( headers, toc_info,
					msg_offset, common.msg_no, replies, OUTPUT )
					headers = None
					# Blank line separates headers and body
					# of message text
					print >> OUTPUT
				else:
					# Message header
					headers.add_line(line)

			else:
				if attachments_dir and re_attachment.search( line ):
					handle_attachment( line, target, 
							   attachments_dir, OUTPUT,
							   common.msg_no, common.line_no )
				else:
					# Message body, simply output the line.
					# Since it's not stripped, don't add 
					# line end
					print >> OUTPUT, strip_linesep( line )
				last_file_position = INPUT.tell()

	# Check if the file isn't empty and any messages have been processed.
	if common.line_no == 0:
		log.warn( 'empty file', common.msg_no, common.line_no )
	elif common.msg_no == 0:
		log.error( 'no messages (not a Eudora mailbox file?)',
			   common.msg_no, common.line_no )

	# For debugging and comparison with a:
	#
	# 	'grep "^From ???@???" file.mbx | wc -l | awk '{ print $1 }'
	#
	#log_msg ("total number of message(s): $common.msg_no")
 
	if common.msg_no == 0: msg_str = '          no messages' 
	if common.msg_no == 1: msg_str = 'total:     1 message' 
	if common.msg_no >= 1: msg_str = 'total: %(common.msg_no)5d messages' % vars()

	warn_err_str = warn.summary() + ', ' + log.summary()

	if verbose >= 0:
		print '    ' + msg_str + '( ' + warn_err_str + ' )'

	# Finish up. Close failures usually indicate filesystem full.
	if INPUT:
		try:
			INPUT.close()
		except IOError:
			return fatal( P + ': cannot close "' + mbx + '"' )

	del log

	return 0


def handle_attachment( line, target, attachments_dir, OUTPUT, msg_no, line_no ):
	"""
	Mac versions put "Attachment converted", Windows (Lite) has
	"Attachment Converted". 

	Next comes a system-dependent path to the attachment binary.
	On mac version, separated by colons, starts with volume, but omits
	path elements between:

	Eudora Folder:Attachments Folder. 

	Windows versions have a full DOS path name to the binary
	(Lite version uses 8-char filenames)
	
	This replaces that filepath with a file URI to the file in the
	attachments_dir directory.  This has no direct effect in Kmail, but 
	sometimes Pine can open the file (so long as there aren't any 
	spaces in the filepath).  At least it makes more sense than
	leaving the old filepath.
	"""
	re_dos_path_beginning = re.compile( r'.*:\\.*' )
	# Mac 1.3.1 has e.g. (Type: 'PDF ' Creator: 'CARO')
	# Mac 3.1 has e.g (PDF /CARO) (00000645)

	# Don't like this.  Too greedy for parentheses.
	re_mac_info = re.compile( r'(.*?)\s(\(.*?\)).*$' )

	attachment_desc = re_attachment.sub( '\\1', line )
	name = ''
	# if has :\, must be windows
	etc = ''
	if re_dos_path_beginning.match( attachment_desc ):
		desc_list = attachment_desc.split( "\\" ) # DOS backslashes
		name = desc_list.pop().strip()	# pop off last portion of name
		if name[-1] == '"':
			name = name[:-1]
	elif re_mac_info.match( line ):
		name = re_mac_info.sub( '\\1', line )
		etc = re_mac_info.sub( '\\2', line ).strip() 
		dlist = name.split( ":" ) # Mac path delim
		name = dlist.pop().strip()	# pop off last portion of name
	else:
		print >> OUTPUT, "FAILED to convert attachment: \'" + attachment_desc + "\'"
		warn.record( "FAILED to convert attachment: \'"
				+ attachment_desc + "\'" , common.msg_no, common.line_no )
	if len( name ) > 0:
		file = os.path.join( target, attachments_dir, name )
		if not os.path.isabs( target ):
			file = os.path.join( os.environ['HOME'], file )
		file = urllib.quote( file )
		print >> OUTPUT, 'Attachment converted: <file://' + file + '> ' + etc

#import profile
# File argument (must be exactly 1).
if sys.argv[0].find( 'Eudora2Mbox.py' ) > -1:	# i.e. if script called directly
	#profile.run( 'convert( sys.argv[1] )' )
	try:
		opts, args = getopt.getopt( sys.argv[1:], 'a:d:t:' )
		if len( args ) < 1 or len( args[0].strip() ) == 0:
			sys.exit( 1 )

		convert( args[0], opts )
	except getopt.GetoptError:
		exit_code = 1
	sys.exit( exit_code )

# Efficency
# ---------
# 
# Appears that the bulk of the time is spent in I/O.  Shaved off
# maybe 10% by reducing number of string copies, but to compare 
# collect_replies and convert, seems the former takes just about half
# what the latter takes, but the former does much less processing--
# but it only reads, while the latter reads and writes.

# Profiler results on a very big mailbox
#    total: 419 messages( total: 8 warnings, no errors )
#         42523 function calls in 20.100 CPU seconds
	
#ncalls  tottime  percall  cumtime  percall filename:lineno(function)
# 10716    0.520    0.000    0.670    0.000 Eudora2Unix.py:224(add)
#  9874    0.290    0.000    0.290    0.000 Eudora2Unix.py:235(getValue)
#  9862    0.170    0.000    0.170    0.000 Eudora2Unix.py:241(setValue)
#   419    0.120    0.000    0.120    0.000 Eudora2Unix.py:253(emit)
#  9873    0.280    0.000    0.280    0.000 Eudora2Unix.py:262(Header:parse)
#     1    5.690    5.690    5.690    5.690 Eudora2Unix.py:292(collect_replies)
#     1    0.050    0.050    0.050    0.050 Eudora2Unix.py:336(collect_toc_info)
#   419    0.220    0.001    0.480    0.001 Eudora2Unix.py:368(emit_headers)
#     1   12.660   12.660   20.090   20.090 Eudora2Unix.py:566(convert)
#     1    0.010    0.010   20.100   20.100 profile:0(convert( sys.argv[1] ))

# (everything else too small to report)

# Tried different matches for message start, including pre-compiled
# regexp that should have just checked the first few chars, but it was
# substantially slower than the string native find.
