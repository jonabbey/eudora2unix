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
import traceback
from HTMLParser import HTMLParseError
from email import message, encoders
from email.mime.multipart import MIMEMultipart
from email.mime.nonmultipart import MIMENonMultipart
from email.mime.application import MIMEApplication
from email.mime.text import MIMEText
from email.mime.image import MIMEImage
from email.mime.message import MIMEMessage
from email.mime.audio import MIMEAudio
from mailbox import mbox
import mimetypes

from Header import Replies, TOC_Info, Header, strip_linesep, re_message_start
import EudoraLog
from EudoraHTMLParser import *

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

message_count = 0

re_quoted_attachment = re.compile( r'^Attachment converted: "([^"]*)"\s*$', re.IGNORECASE )
re_attachment = re.compile( r'^Attachment converted: (.*)$', re.IGNORECASE )
re_embedded = re.compile( r'^Embedded Content: ([^:]+):.*' )
re_multi_contenttype = re.compile( r'multipart/([^;]+);.*', re.IGNORECASE )
re_single_contenttype = re.compile( r'^([^;]+);?.*', re.IGNORECASE )
re_charset_contenttype = re.compile( r'charset="([^"]+)"', re.IGNORECASE )
re_boundary_contenttype = re.compile( r'boundary="([^"]+)"', re.IGNORECASE )
re_contenttype = re.compile( r'content-type', re.IGNORECASE )
re_xflowed = re.compile( r'</?x-flowed>')
re_xhtml = re.compile( r'</?x-html>' )
re_pete_stuff = re.compile( r'<!x-stuff-for-pete[^>]+>' )
re_filename_cleaner = re.compile( r'^(.*\.\S+).*$' )
re_cids_finder = re.compile(r'<img src="cid:([^"]+)"', re.IGNORECASE)

# Don't like this.  Too greedy for parentheses.
re_mac_info = re.compile( r'(.*?)\s(\(.*?\)).*$' )
re_dos_path_beginning = re.compile( r'.*:\\.*' )

re_initial_whitespace = re.compile( r'^[ \t]+(.*?)$' )

mimetypes.init()

scrub_xflowed = True
attachments_listed = 0
attachments_found = 0
attachments_missing = 0
paths_found = {}
paths_missing = {}
missing_attachments = {}
found_attachments = {}
attachments_dirs = []

edir = None

def convert( mbx, embedded_dir = None, opts = None ):
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

	global attachments_listed, attachments_found, attachments_missing, attachments_dirs

	global paths_found, paths_missing, message_count

	global re_initial_whitespace

	global edir

	attachments_listed = 0
	attachments_found = 0
	attachments_missing = 0

	edir = embedded_dir

	print "Converting %s" % (mbx,)

	if not mbx:
		EudoraLog.fatal( P + ': usage: Eudora2Mbox.py eudora-mailbox-file.mbx' )
		return 0

	attachments_dirs = []
	target = ''
	if opts:
		for f, v in opts:
			if f == '-a':
				attachments_dirs = v.split(':')

			elif f == '-t':
				target = v

	EudoraLog.msg_no	= 0	# number of messages in this mailbox
	EudoraLog.line_no	= 0	# line number of current line record (for messages)

	headers = None
	in_headers = False
	last_file_position = 0
	msg_offset = 0
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

	msg_lines = []
	attachments = []
	embeddeds = []
	message = None
	is_html = False
	attachments_ok = False

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
		# if the line does *not* begin with 'Find '.
		#
		# I'm not sure what the original author was trying to
		# avoid here with the test for 'Find '..

		if line.find( 'Find ', 0, 5 ) and re_message_start.match( line ):
			if in_headers:
				# Error
				#
				# We have a "From " line while already 
				# _in_ the headers. The previous message is 
				# probably empty and does not have the required
				# empty line to terminate the message
				# headers and start the message body.
				# Finally, emit this as a message
				#
				EudoraLog.log.error( 'Message start found inside message')

			if headers:
				message = craft_message(msg_lines, headers, attachments, embeddeds, mbx, is_html)

				try:
					newmailbox.add(message)
				except TypeError:
					print str(headers)
					traceback.print_exc(file=sys.stdout)

				message_count = message_count + 1

			msg_offset = last_file_position
			headers = Header()
			headers.add( 'From ', line[5:].strip() )
			in_headers = True
			is_html = False
			EudoraLog.msg_no += 1
		else:
			if in_headers:
				if re_initial_whitespace.match( line ):
					# Header "folding" (RFC 2822 3.2.3)
					headers.appendToLast( line )
				elif len( line.strip() ) != 0:
					# Message header
					headers.add_line(line)
				else:
					# End of message headers.
					
					# scrub the header lines we've scanned

					headers.clean(toc_info, msg_offset, replies)

					in_headers = False

					# prep to start scanning lines
					# in the body of the message

					msg_lines = []
					embeddeds = []
					attachments = []
			else:
				# We're in the body of the text

				if re_xhtml.search ( line ):
					is_html = True
				
				if attachments_dirs and re_attachment.search( line ):
					# remove the newline that
					# Eudora inserts before the
					# 'Attachment Converted' line.

					if len(msg_lines) > 0 and (msg_lines[-1] == '\n' or msg_lines[-1] == '\r\n'):
						msg_lines.pop()

					#EudoraLog.log.warn("Adding attachment with contenttype = " + contenttype)
					attachments.append( (line, target) )
				else:
					embedded_matcher = re_embedded.match ( line )
					
					if embedded_matcher:
						filename = embedded_matcher.group(1)
						embeddeds.append( filename )
					else:
						if scrub_xflowed:
							line = re.sub(re_xflowed, '', line)
							line = re.sub(re_xhtml, '', line)
							line = re.sub(re_pete_stuff, '', line)

						msg_lines.append(strip_linesep(line) + "\n")

				last_file_position = INPUT.tell()

	# Check if the file isn't empty and any messages have been processed.
	if EudoraLog.line_no == 0:
		EudoraLog.log.warn( 'empty file' )
	elif EudoraLog.msg_no == 0:
		EudoraLog.log.error( 'no messages (not a Eudora mailbox file?)' )

	# For debugging and comparison with a:
	#
	# 	'grep "^From ???@???" file.mbx | wc -l | awk '{ print $1 }'
	#
	#log_msg ("total number of message(s): $EudoraLog.msg_no")

	print

	print "\nMissing path count:"

	for (path, count) in paths_missing.iteritems():
		print "%s: %d" % (path, count)

	print "\nFound path count:"

	for (path, count) in paths_found.iteritems():
		print "%s: %d" % (path, count)
 
	print "\n------------------------------"
	print "Attachments Listed: %d\nAttachments Found: %d\nAttachments Missing:%d" % (attachments_listed, attachments_found, attachments_missing)
	print "------------------------------"

	if EudoraLog.msg_no == 0: msg_str = 'total: Converted no messages' 
	if EudoraLog.msg_no == 1: msg_str = 'total: Converted 1 message' 
	if EudoraLog.msg_no >= 1: msg_str = 'total: Converted %d messages' % (EudoraLog.msg_no,)

	print msg_str

	if EudoraLog.verbose >= 0:
		print EudoraLog.log.summary()

	# Finish up. Close failures usually indicate filesystem full.

	if newmailbox:
		newmailbox.close()

	if INPUT:
		try:
			INPUT.close()
		except IOError:
			return EudoraLog.fatal( P + ': cannot close "' + mbx + '"' )

	return 0

def craft_message( msg_lines, headers, attachments, embeddeds, mbx, is_html ):
	"""This function handles the creation of a Python email.message
	object from the msg_lines and headers lists created during the main
	loop."""

	global edir

	embeddedcids = []

	if msg_lines:
		msg_text = ''.join(msg_lines)
	else:
		msg_text = ''

	contenttype = headers.getValue('Content-Type:')

	if not contenttype:
		msattach = headers.getValue('X-MS-Attachment:')

		if msattach:
			message = MIMEMultipart()
			attachments_ok = "Dunno"
			attachments_contenttype = "Still Dunno"
		else:
			message = MIMENonMultipart('text', 'plain')
			attachments_ok = False
			attachments_contenttype = False
#			print "T",
	elif not re_multi_contenttype.search( contenttype ):
		if re_single_contenttype.search ( contenttype ):
			mimetype = re_single_contenttype.sub( r'\1', contenttype )
			print "HEYNYEHYHEYSDF mimetype = %s" % (mimetype,)
			(main, slash, sub) = mimetype.partition( '/' )
			print "HEYNYEHYHEYSDF main, sub = %s,%s" % (main,sub)
			if main == 'message':
				print msg_text
				headers, content = msg_text.split("\r\n\r\n", 1)
				print "HEY headers = %s\n\nHEY body = %s" % (headers, content)
				message = MIMEMessage(main, sub)
			else:
				message = MIMENonMultipart(main, sub)
			attachments_ok = False
			attachments_contenttype = False
#			print "X",
		else:
			print "*** %s" % (contenttype,)
	else:
		subtype = re_multi_contenttype.search( contenttype )
		if subtype:
			message = MIMEMultipart(_subtype=subtype.group(1))
			attachments_ok = subtype.group(1)
			attachments_contenttype = contenttype
#			print "Y",
		else:
			message = MIMEMultipart()
#			print "Z",
			attachments_ok = "Dunno"
			attachments_contenttype = "Still Dunno"

	# Need to add support here for processing embeddeds

	if embeddeds:
		if not isinstance( message, MIMEMultipart):
			print "\n\n==================================================\n"
			print "Found surprise multipart for embeddeds!\n"

			message = MIMEMultipart(_subtype='related')
		else:
			print "\n\n==================================================\n"
			print "Found embeddeds in multipart!\n"


		p = EudoraHTMLParser()

		try:
			p.feed(msg_text)
			cids = p.get_cids()
		except HTMLParseError:
			# okay, we've got unparseable HTML here.
			# Let's just use a quick regexp to see if we can make sense of this.

			cids = []

			for match in re_cids_finder.finditer(msg_text):
				cids.append("cid:" + match.group(1))

		if not len(cids) == len(embeddeds):
			print "cids / embeddeds mismatch!"
			print
			print mbx

			for piece in ['To:', 'From:' , 'Subject:', 'Date:']:
				if headers.getValue(piece):
					print piece + " " + headers.getValue(piece)[:80]
			print

		print "\tcid\t\t\t\t\t\t\tembedded"



		i = 0
		while i < len(cids) or i < len(embeddeds):
			if i < len(cids):
				print "%d.\t%s" % (i, cids[i]),
				print "\t" * (6 - (len(cids[i]) // 8)),

			else:
				print "%d.\t" % (i, ),
				print "\t\t\t\t\t\t",
			if i < len(embeddeds):
				print embeddeds[i],

				if os.path.exists(edir + os.sep + embeddeds[i]):
					print " *"
				else:
					print " !"
			else:
				print

			i = i + 1

		cidi = 0
		embeddedi = 0
		cidsmatched = set()
		while cidi < len(cids) or embeddedi < len(embeddeds):
			if cidi < len(cids) and embeddedi < len(embeddeds):
				if cids[cidi].startswith('cid:'):
					actualcid = cids[cidi][4:]
				else:
					actualcid = cids[cidi]

				# the document might have several img
				# references to the same cid.. we
				# don't want to try to mate up
				# multiple inline files in that case

				if actualcid in cidsmatched:
					cidi = cidi + 1
				else:
					cidsmatched.add(actualcid)
					embeddedcids.append( (actualcid, embeddeds[embeddedi]) )
					embeddedi = embeddedi + 1
					cidi = cidi + 1
			else:
				if embeddedi < len(embeddeds):
					embeddedcids.append( (None, embeddeds[embeddedi]) )
					embeddedi = embeddedi + 1
				else:
					# we have more cids than
					# embeddeds, keep looping
					# through
					cidi = cidi + 1


		print "\n\nAttaching inline components:"

		for c, f in embeddedcids:
			print "%s\t%s" % (c, f)

		print "\n==================================================\n"

	if attachments:
		if not isinstance( message, MIMEMultipart):
			#print "\n\n%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%\n"
			#print "Forcing surprise multipart!\n"
			#print "\n%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%\n"

			message = MIMEMultipart()

	# bind the headers into our message

	set_headers( message, headers )


	try:
		if  not isinstance( message, MIMEMultipart):
			message.set_payload(msg_text)
		else:
			if is_html:
				message.attach(MIMEText(msg_text, _subtype='html'))
			else:
				message.attach(MIMEText(msg_text))
	except Exception, e:
		print "\nHEY HEY HEY message = " + str(msg_text) + "\n"
		print "Type of message's payload is " + str(type(message.get_payload())) + "\n"
		if isinstance( message.get_payload(), list ):
			print "Size of message's payload list is " + str(len(message.get_payload())) + "\n"
			print ")))))))))))))))))))) First part"
			print str(message.get_payload()[0])
			print ">>>>>>>>>>>>>>>>>>>> Second part"
			print str(message.get_payload()[1])

		print "attachments_contenttype is (%s)" % (attachments_contenttype, )
		print "attachments_ok is (%s)" % (attachments_ok, )

		if attachments:
			print "Yeah, attachments were found: %d" % (len(attachments), )

		print "EXCEPTION " + str(e) + "\n"
		traceback.print_exc(file=sys.stdout)

	if attachments:
		for aline, atarget in attachments:
			handle_attachment( aline, atarget, message )

	if embeddedcids:
		for cid, filename in embeddedcids:
			handle_embedded(cid, filename, message)

	return message


def set_headers( message, headers):
	for header, value in headers:
		if header != 'From ' and not re_contenttype.match( header ):
			newheader = header[:-1]
			message[newheader] = value

	myfrom = headers.getValue('From ')
					
	message.set_unixfrom('From ' + myfrom)

def handle_attachment( line, target, message ):
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
	attachments_dirs directories.  This has no direct effect in Kmail, but 
	sometimes Pine can open the file (so long as there aren't any 
	spaces in the filepath).  At least it makes more sense than
	leaving the old filepath.
	"""

	global attachments_listed, attachments_found, attachments_missing, attachments_dirs
	global paths_found, paths_missing
	global missing_attachments, found_attachments

	attachments_listed = attachments_listed + 1

	# Mac 1.3.1 has e.g. (Type: 'PDF ' Creator: 'CARO')
	# Mac 3.1 has e.g (PDF /CARO) (00000645)

	if re_quoted_attachment.match(line):
		attachment_desc = re_quoted_attachment.sub( '\\1', line )
	else:
		attachment_desc = re_attachment.sub( '\\1', line )

	if attachment_desc.find('"') != -1:
		print "**>>**", attachment_desc

	attachment_desc = strip_linesep(attachment_desc)

	# some of John's attachment names have an odd OutboundG4:
	# prefix which is not present in the filenames on disk..

	if attachment_desc.find('OutboundG4:') != -1:
		attachment_desc = attachment_desc.replace('OutboundG4:', '')

	name = ''
	# if has :\, must be windows
	etc = ''
	if re_dos_path_beginning.match( attachment_desc ):
		desc_list = attachment_desc.split( "\\" ) # DOS backslashes
		name = desc_list.pop().strip()	# pop off last portion of name
		orig_path = "/".join(desc_list)
		if name[-1] == '"':
			name = name[:-1]
	elif re_mac_info.match( line ):
		name = re_mac_info.sub( '\\1', line )
		etc = re_mac_info.sub( '\\2', line ).strip() 
		dlist = name.split( ":" ) # Mac path delim
		name = dlist.pop().strip()	# pop off last portion of name
		orig_path = "/".join(dlist)
	else:
#		EudoraLog.log.warn( "FAILED to convert attachment: \'"
#				    + attachment_desc + "\'" )
		name = attachment_desc
		orig_path = attachment_desc

	if len( name ) <= 0:
		return

	filename = None

	for adir in attachments_dirs:
		if not filename or not os.path.exists(filename):
			filename = os.path.join( target, adir, name )
			if not os.path.isabs( target ):
				filename = os.path.join( os.environ['HOME'], filename )

			if not os.path.exists(filename):
				if name.startswith('OutboundG4:'):
					name = name[11:]
					print "**** Hey, name is now %s" % (name, )
					filename = os.path.join(target, attachments_dir, name)

			# our user has attachments that have / characters in
			# the file name, but when they got copied over to
			# unix, the / chars were taken out, if it would help.

			if not os.path.exists(filename):
				if name.find('/') != -1:
					name=name.replace('/','')
					filename = os.path.join(target, adir, name)

			# our user also has attachments that have _ characters
			# in the file name where the file on disk has spaces.
			# translate that as well, if it would help.

			if not os.path.exists(filename):
				if name.find('_') != -1:
					name = name.replace('_', ' ')
					filename = os.path.join(target, adir, name)

			# our user actually also has attachments that have
			# space characters in the file name where the file on
			# disk has underscores.  if we didn't find the match
			# after our last transform, try the rever

			if not os.path.exists(filename):
				if name.find(' ') != -1:
					name = name.replace(' ', '_')
					filename = os.path.join(target, adir, name)

	# in our user's attachments, we have some files named
	# akin to 'filename.ppt 1' and so forth.  we're going
	# to trim anything after the first whitespace
	# character after the first . in the filename

	cleaner_match = re_filename_cleaner.match( filename )

	if cleaner_match:
		filename = cleaner_match.group(1)

	mimeinfo = mimetypes.guess_type(filename)

	if not os.path.exists(filename):
		cleaner_match = re_filename_cleaner.match(filename.replace('_', ' '))

		if cleaner_match and os.path.exists(cleaner_match.group(1)):
			filename = cleaner_match.group(1)

	if not mimeinfo[0]:
		(mimetype, mimesubtype) = ('application', 'octet-stream')
	else:
		(mimetype, mimesubtype) = mimeinfo[0].split('/')

	if os.path.isfile(filename):
		fp = open(filename, 'rb')

		try:
			if mimetype == 'application' or mimetype == 'video':
				msg = MIMEApplication(fp.read(), _subtype=mimesubtype)
			elif mimetype == 'image':
				msg = MIMEImage(fp.read(), _subtype=mimesubtype)
			elif mimetype == 'text':
				msg = MIMEText(fp.read(), _subtype=mimesubtype)
			elif mimetype == 'audio':
				msg = MIMEAudio(fp.read(), _subtype=mimesubtype)
			else:
				EudoraLog.log.error("Unrecognized mime type '%s' while processing attachment '%s'" % (mimeinfo[0], filename))
				return
		finally:
			fp.close()

		msg.add_header('Content-Disposition', 'attachment', filename=name)

		message.attach(msg)

		attachments_found = attachments_found + 1

#		EudoraLog.log.warn(" SUCCEEDED finding attachment: \'" + attachment_desc + "\', name = \'" + name + "\'")
		if orig_path in paths_found:
			paths_found[orig_path] = paths_found[orig_path] + 1
		else:
			paths_found[orig_path] = 1

		if not EudoraLog.log.mbx_name() in found_attachments:
			found_attachments[EudoraLog.log.mbx_name()] = []
		found_attachments[EudoraLog.log.mbx_name()].append((attachment_desc, filename))
	else:
		attachments_missing = attachments_missing + 1

		if not EudoraLog.log.mbx_name() in missing_attachments:
			missing_attachments[EudoraLog.log.mbx_name()] = []
		missing_attachments[EudoraLog.log.mbx_name()].append(attachment_desc)

#		EudoraLog.log.warn(" FAILED to find attachment: \'" + attachment_desc + "\'" )

		if orig_path in paths_missing:
			paths_missing[orig_path] = paths_missing[orig_path] + 1
		else:
			paths_missing[orig_path] = 1

def handle_embedded( cid, filename, message ):
	global edir
	global attachments_listed, attachments_found, attachments_missing, attachments_dirs
	global paths_found, paths_missing
	global missing_attachments, found_attachments

	realfilename = edir + os.sep + filename

	if not os.path.exists(realfilename):
		print "Couldn't find embedded file %s" % (realfilename,)
		return

	mimeinfo = mimetypes.guess_type(realfilename)

	if not mimeinfo[0]:
		(mimetype, mimesubtype) = ('application', 'octet-stream')
	else:
		(mimetype, mimesubtype) = mimeinfo[0].split('/')

	if os.path.isfile(realfilename):
		fp = open(realfilename, 'rb')

		try:
			if mimetype == 'application' or mimetype == 'video':
				msg = MIMEApplication(fp.read(), _subtype=mimesubtype)
			elif mimetype == 'image':
				msg = MIMEImage(fp.read(), _subtype=mimesubtype)
			elif mimetype == 'text':
				msg = MIMEText(fp.read(), _subtype=mimesubtype)
			elif mimetype == 'audio':
				msg = MIMEAudio(fp.read(), _subtype=mimesubtype)
			else:
				EudoraLog.log.error("Unrecognized mime type '%s' while processing attachment '%s'" % (mimeinfo[0], filename))
				return
		finally:
			fp.close()

		if cid:
			msg.add_header('Content-ID', cid)
			msg.add_header('Content-Disposition', 'inline', filename=filename)
		else:
			msg.add_header('Content-Disposition', 'attachment', filename=filename)

		message.attach(msg)


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

