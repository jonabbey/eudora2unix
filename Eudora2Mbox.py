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
__date__ = "2010-11-01"
__version__ = "2.0"
__credits__ = """
	Based on Eudora2Unix.pl by Eric Maryniak <e.maryniak@pobox.com>;
	based in turn on eud2unx.pl by Blake Hannaford"""
import os
import re
import sys
import string
import getopt
import urllib
from email import message
from email.mime.multipart import MIMEMultipart
from email.mime.nonmultipart import MIMENonMultipart
from mailbox import mbox

from Header import Replies, TOC_Info, Header, strip_linesep, re_message_start
import EudoraLog

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
# ================================================================================
#
# Efficency
# ---------
# 
# Appears that the bulk of the time is spent in I/O.  Shaved off
# maybe 10% by reducing number of string copies, but to compare 
# collect_replies and convert, seems the former takes just about half
# what the latter takes, but the former does much less processing--
# but it only reads, while the latter reads and writes.

# (everything else too small to report)

# Tried different matches for message start, including pre-compiled
# regexp that should have just checked the first few chars, but it was
# substantially slower than the string native find.

if sys.hexversion < 33686000:
	sys.stderr.write( "Aborted: Python version must be at least 2.2.1" \
		+ os.linesep )
	sys.exit( 1 )

# Program name and title in various banners.
P = sys.argv[0]

exit_code = 0	# exit code: 0 if all ok, 1 if any warnings or errors

re_attachment = re.compile( '^Attachment converted: (.*?)$', re.IGNORECASE )
re_multi_contenttype = re.compile( r'^Content-Type: multipart/([^;]+);.*', re.IGNORECASE )
re_single_contenttype = re.compile( r'^Content-Type: ([^;]+);', re.IGNORECASE )
re_charset_contenttype = re.compile( r'charset="([^"]+)"', re.IGNORECASE )
re_boundary_contenttype = re.compile( r'boundary="([^"]+)"', re.IGNORECASE )

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

	print "Converting %s" % (mbx,)

	if not mbx:
		EudoraLog.fatal( P + ': usage: Eudora2Mbox.py eudora-mailbox-file.mbx' )
		return 0

	attachments_dir = None
	target = ''
	if opts:
		for f, v in opts:
			if f == '-a':
				attachments_dir = v
			elif f == '-t':
				target = v

	EudoraLog.msg_no	= 0	# number of messages in this mailbox
	EudoraLog.line_no	= 0	# line number of current line record (for messages)

	headers = None
	last_file_position = 0
	msg_offset = 0

	re_initial_whitespace = re.compile( r'^[ \t]+(.*?)$' )

	EudoraLog.log = EudoraLog.Log( mbx )

	try:
		INPUT = open( mbx, 'r' )
	except IOError, ( errno, strerror ):
		INPUT = None
		return EudoraLog.fatal( P + ': cannot open "' + mbx + '", ' + strerror )

	newfile = mbx + '.new'

	try:
		newmailbox = mbox( newfile )
	except IOError, ( errno, strerror ):
		mailbox = None
		return EudoraLog.fatal( P + ': cannot open "' + newfile + '", ' + strerror )

	toc_info = TOC_Info( mbx )
	replies = Replies( INPUT )

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
		EudoraLog.line_no += 1

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
				EudoraLog.log.error( 'Message start found inside message',
						     EudoraLog.msg_no, EudoraLog.line_no )
				#emit_headers( headers, toc_info,
				#	      msg_offset, EudoraLog.msg_no, replies, OUTPUT )

			msg_offset = last_file_position
			headers = Header()
			headers.add( 'From ', line[5:].strip() )
			EudoraLog.msg_no += 1
		else:
			if headers:
				if re_initial_whitespace.match( line ):
					# Header "folding" (RFC 2822 3.2.3)
					headers.appendToLast( line )
				elif len( line.strip() ) != 0:
					# Message header
					headers.add_line(line)
				else:
					# End of message headers.

					# here is where we could
					# create the message

					contenttype = headers.getValue('content-type')

					if not contenttype:
						message = MIMENonMultipart('text', 'plain')
					elif not re_multi_contenttype.search( contenttype ):
						if re_single_contenttype.search ( contenttype ):
							mimetype = re_single_contenttype.sub( r'\1', contenttype )
							(main, slash, sub) = mimetype.partition( '/' )
							message = MIMENonMultipart(main, sub)
					else:
						subtype = re_multi_contenttype.sub( r'\1', contenttype )
						if subtype:
							message = MIMEMultipart(_subtype=subtype)
						else:
							message = MIMEMultipart()

					# set all the headers we've seen

					headers.clean(toc_info, msg_offset, replies)

					for header, value in headers:
						if header != 'From ':
							newheader = header[:-1]
							message[newheader] = value

					myfrom = headers.getValue('From ')

					message.set_unixfrom('From ' + headers.getValue('From '))

					print str(message)

					headers = None
			else:
				if False and attachments_dir and re_attachment.search( line ):
					handle_attachment( line, target, 
							   attachments_dir, OUTPUT,
							   EudoraLog.msg_no, EudoraLog.line_no )
				else:
					# Message body, simply output the line.
					# Since it's not stripped, don't add 
					# line end
					print strip_linesep( line )
				last_file_position = INPUT.tell()

	# Check if the file isn't empty and any messages have been processed.
	if EudoraLog.line_no == 0:
		EudoraLog.log.warn( 'empty file', EudoraLog.msg_no, EudoraLog.line_no )
	elif EudoraLog.msg_no == 0:
		EudoraLog.log.error( 'no messages (not a Eudora mailbox file?)',
				     EudoraLog.msg_no, EudoraLog.line_no )

	# For debugging and comparison with a:
	#
	# 	'grep "^From ???@???" file.mbx | wc -l | awk '{ print $1 }'
	#
	#log_msg ("total number of message(s): $EudoraLog.msg_no")
 
	if EudoraLog.msg_no == 0: msg_str = '          no messages' 
	if EudoraLog.msg_no == 1: msg_str = 'total:     1 message' 
	if EudoraLog.msg_no >= 1: msg_str = 'total: %(EudoraLog.msg_no)5d messages' % vars()

	warn_err_str = warn.summary() + ', ' + EudoraLog.log.summary()

	if EudoraLog.verbose >= 0:
		print '    ' + msg_str + '( ' + warn_err_str + ' )'

	# Finish up. Close failures usually indicate filesystem full.
	if INPUT:
		try:
			INPUT.close()
		except IOError:
			return EudoraLog.fatal( P + ': cannot close "' + mbx + '"' )

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
				+ attachment_desc + "\'" , EudoraLog.msg_no, EudoraLog.line_no )
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

