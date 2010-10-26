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

""" Suffixes for intermediate and log files."""
OUT_SFX = '.E2U_OUT'
LOG_SFX = '.E2U_LOG'
ERR_SFX = '.E2U_ERR'
WARN_SFX = '.E2U_WARN'

# Configuration.

# Verbosity.
# Determines if subroutines {log,warn,err}_msg send output to stdout, too:
#
#     verbose = -1  # ultra quiet: not even the mailbox's message total
#     verbose =  0  # really quiet
#     verbose =  1  # errors only
#     verbose =  2  # warnings and errors only
#     verbose =  3  # logging, warnings and errors
#
verbose = 0

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

#
# Help functions.
#

# SW
class Message:
	"""Opens message file with reasonable suffix, records messages in it
	(depending on verbosity, also prints on stdout),
	summarizes messages recorded, and closes file."""
	total_msgs = 0

	def __init__( self, mbx, suffix, kindstr, verbosity ):
		self.mbxname = mbx
		self.file_suffix = suffix
		self.filename = mbx + suffix
		self.kindstr = kindstr
		self.verbosity_threshold = verbosity
		self.OUT = None
		self.last_msg = 0
		self.n_msgs = 0
		
	def record( self, msg, msg_no, line_no ):
		global P, exit_code, verbose
		msg += os.linesep
		self.last_msg = self.n_msgs
		out = self.mbxname + ' (msg #' + `msg_no` + ', line #' \
				+ `line_no` + '):' + os.linesep + msg
		if verbose >= self.verbosity_threshold:
			print out
		if not self.OUT:
			try:
				self.OUT = open( self.filename, 'w' )
			except IOError, ( errno, strerror ):
				return fatal( P + ': cannot open "' 
				+ self.filename + '"' + ": " + strerror )
		self.OUT.write( out + os.linesep )
		self.OUT.flush()
		Message.total_msgs += 1
		self.n_msgs += 1
		exit_code = 1

	def summary( self ):
		if self.n_msgs == 0: return 'no ' + self.kindstr + 's' 
		if self.n_msgs == 1: return '1 ' + self.kindstr 
		if self.n_msgs >= 1: return `self.n_msgs` + ' ' \
							+ self.kindstr + 's'
	def __del__( self ):
		try:
			if self.OUT:
				self.OUT.close()
		except IOError:
			return fatal( P + ': cannot close "' + self.filename 
								+ '"' )
class LogMessage( Message ):
	def __init__( self, mbx ):
		Message.__init__( self, mbx, LOG_SFX, 'log', 3 )

class WarnMessage( Message ):
	def __init__( self, mbx ):
		Message.__init__( self, mbx, WARN_SFX, 'warning', 2 )

class ErrMessage( Message ):
	def __init__( self, mbx ):
		Message.__init__( self, mbx, ERR_SFX, 'error', 1 )

err = None
warn = None
log = None

def fatal( msg ):
	if msg and len( msg ) > 0:
		print >> sys.stderr, msg
	return 1

def iso_8601_zulu():
	"""
	Return a string with the date and time in ISO 8601 form for
	'timezone' Zulu, ie. UTC +00:00, or zero-meridian and formerly
	known as 'GMT', or 'Greenwich Mean Time'.

	See http://www.cl.cam.ac.uk/~mgk25/iso-time.html for more info on
	on the ISO International Standard Date and Time Notation (ISO 8601).

	Example: for February 28, 2002 14:42:42 UTC+01:00, this string:
	    2002-02-28T13:42:42Z
	will be returned and shows the date and time in 'timezone' Zulu.

	Note the one (1) hour difference in this particular example (because
	it is in UTC +01:00), the 'T' separator between date and time and the
	'Z' (Zulu) designator for the UTC +00:00 'timezone'.
	CVS, a popular source code and document versioning program, also uses
	Zulu time."""
	(gm_year, gm_month, gm_day, 
		gm_hour, gm_minute, gm_second, 
		gm_weekday, gm_julian_day, gm_dstf) = time.gmtime()

	iso_8601_zulu_datetime = "%04d-%02d-%02dT%02d:%02d:%02dZ" % \
		(gm_year+1900, gm_month+1, gm_day, 
		gm_hour, gm_minute, gm_second)

	return iso_8601_zulu_datetime

def strip_linesep( line ):
	"""Regular expressions proved too slow, and rstrip doesn't take
	an argument in my distribution (?)"""
	while len( line ) > 0 and ( line[-1] == '\n' or line[-1] == '\r' ):
		line = line[0:-1]
	return line
# SW
class Header:
	"""
	A list of mailbox headers.
	Implements case-insensitive searching (RFC 561 explicitly states
	case of headers is undefined); keeps a mixed-case version for output.

	A dictionary (hash, in Perl) doesn't work for this because several
	header lines can share the same key, e.g. 'Received:'.

	Three fields used:
		lowercase-id, id, value
	The first is for searching by id, the second is to make id output
	like the input.
	"""
	def __init__( self ):
		self.data = []
		self.index = 0
	
	def __iter__( self ):
		return self

	def add( self, id, value ):
		"""Will also accept un-parsed line"""
		if not id or len( id ) == 0:
			return
		value = self.stripOffID( id, value )
		self.data.append( [ id.lower(), id, value ] )

	def getValue( self, id ):
		lcid = id.lower()
		for h in self.data:
			if h[0] == lcid:
				return h[2]
		return None

	def stripOffID( self, id, line ):
		idlen = len( id )
		if idlen == 0:
			return
		lcid = id.lower()
		if line and len( line ) >= idlen:
			linefront = line[ 0:idlen ].lower()
			if linefront == lcid:
				line = line[ idlen: ].strip()
		return line

	def setValue( self, id, value ):
		idlen = len( id )
		if idlen == 0:
			return
		lcid = id.lower()
		if self.getValue( id ):
			for h in self.data:
				if h[0] == lcid:
					h[2] = self.stripOffID( id, value )
					break
		else:
			self.add( id, value )

	def appendToLast( self, additional ):
		"""Facilitates header field "folding" (RFC 2822 3.2.3)"""
		# strangely, a raw tab after os.linesep doesn't get printed...
		if len( self.data ) == 0:
			return
		additional = strip_linesep( additional )
		self.data[-1][2] += os.linesep + '\t' + additional

	def emit( self, filehandle, exceptions = None ):
		for h in self.data:
			if not exceptions or h[0] not in exceptions:
				filehandle.write( h[1] )
				if h[0] != 'from ':
					filehandle.write( ' ' )
				filehandle.write( h[2] + os.linesep )

	def next( self ):
		if self.index < len( self.data ):
			val = ( self.data[self.index][1],
				self.data[self.index][2] )
			self.index = self.index + 1
			return val
		else:
			raise StopIteration

def parse_header( line ):
	"""Parses a header line into a (key, value) tuple, trimming
	whitespace off ends.  Introductory 'From ' header not treated."""
	colon = line.find( ':' )
	space = line.find( ' ' )

	# If starts with something with no whitespace then a colon,
	# that's the ID.
	if colon > -1 and ( space == -1 or space > colon ):
		id = line[ 0: colon + 1 ]
		value = line[ colon + 1:]
		if value:
			value = value.strip()
		return ( id, value )

	return ( None, None )

date_pat = r'\s*\S+?\s*(\S{3})\s+(\S{3})\s+(\d{1,2})'
time_pat = r'\s*(\d{2}:\d{2}:\d{2})\s+(\d{4})\s*([+-]\d{4}){0,1}'
re_from_date_time = re.compile( date_pat + time_pat )
re_message_start = re.compile( r'^From' + date_pat + time_pat )
# SW
#
class Replies:
	"""
	Eudora seems to rely on a message with In-Reply-To corresponding 
	to the current message Message-ID.
	Pine indicates that a message has been replied to by X-Status: A,

	This reads through whole mailbox, makes dictionary of message ID's
	found in In-Reply-To headers.

	Note: Won't work if reply is in a different mailbox, or otherwise lost.
	"""
	def __init__( self, file ):
		self.replies = {}
		inheaders = False
		# see below for why I don't use a for line in file loop here.
		while True:
			line = file.readline()
			if not line:
				break
			if line.find( 'Find ', 0, 5 ) and re_message_start.match( line ):
				inheaders = True
			else:
				if inheaders:
					line = strip_linesep( line )
					if len( line ) == 0:
						inheaders = False
					else:
						if line.find( 'In-Reply-To:' ) == 0:
							line = line.replace(  
							'In-Reply-To:', '', 1 )
							line = line.strip()
							self.replies[line] = True
		file.seek( 0 )

	def message_was_answered( self, message_id ):
		if len( message_id ) > 0:
			message_id = message_id.strip()

			try:
				self.replies[message_id]
				return True
			except KeyError:
				return False
		return False

# SW
class TOC_Info:
	"""Looks for a file ending in ".toc.txt" to find values of
	Status and X_PRIORITY headers.  See EudoraTOC.py.

	The parsed toc file is text file that represents the contents of
	the binary Eudora '.toc' file corresponding to the mailbox.
	The Status info indicates whether the Eudora message was read or
	not.

	The toc file keeps track of the message by a binary offset to
	the beginning of the message in the mailbox file
	"""
	def __init__( self, mbx_name ):
		self.info = {}
		offset = 0
		status = ''
		toc_file_name = mbx_name + ".toc.txt"
		try:
			TOCFILE = open( toc_file_name )

			# the theory here is that an 'offset:' line in the
			# parsed toc file will always precede the other lines
			# for that message
			for line in TOCFILE:
				if line.find( 'offset:' ) == 0:
					offset = line.replace( 'offset:', '' ).strip()
					self.info[offset] = {}
				elif line.find( 'status:' ) == 0:
					status = line.replace( 'status:', '' ).strip()
					self.info[offset]['status'] = status
				elif line.find( 'priority:' ) == 0:
					pri = line.replace( 'priority:', '' ).strip()
					self.info[offset]['priority'] = pri
			TOCFILE.close()

		except IOError, ( errno, strerror ):
			self.info = None
			if verbose >= 0:
				print( "Couldn't read parsed .toc file '" 
					+ toc_file_name + "': " + strerror )

	def info_exists_for_msg_at( self, offset ):
		try:
			self.info[offset]
			return True
		except Exception:
			return False

	def status_of_msg_at( self, offset ):
		try:
			return self.info[offset]['status']
		except KeyError:
			return None

	def priority_of_msg_at( self, offset ):
		try:
			return self.info[offset]['priority']
		except KeyError:
			return None

weekdays = ( 'Sun', 'Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat' )

def fix_date( date ):
	d = date.split( ' ' )	# 5 date items
	if len( d ) < 5:
		return date	# don't know what to do with this
	if d[0][-1] != ',' and d[0] in weekdays:
		d[0] += ','	# comma must come after weekday
	return string.join( d, ' ' )

def emit_headers( headers, toc, msg_offset, msg_no, replies, OUTPUT ):
	"""
	Processes and prints to OUTPUT the collected headers for the
	current message.

	Argument headers is a Headers object containing all the headers
	found in the current message, the offset to the first character of
	which is in msg_offset.

	The email for the 'From ' (not 'From: ') header is extracted from
	the first encountered 'From: ' or else 'Sender: ' or else
	'Return-Path: ', or else, it is set to 'unknown@unknown.unknown'. 
	This replaces the '???@???' in the 'From ' header.

	If a 'Date: ' is header is not present, a date is extracted from
	header 'From ' and reformatted and a properly rewritten
	'Date: ' header is appended.

	The flag variable $emit_X_Eudora2Unix_Header is used to determine
	if a 'X-Eudora2Unix: ' should be added. It looks like:
		X-Eudora2Unix: 2002-02-28T13:42:42Z converted
	where the date and time (for timezone UTC +00:00, formerly known
	as 'GMT') is in ISO 8601 format (in the so called extended format,
	to be precize). It shows the time and date of conversion of this
	specific message in Zulu (zero-meridian) ISO 8601 date and time.
	See http://www.cl.cam.ac.uk/~mgk25/iso-time.html for more info on
	on the ISO International Standard Date and Time Notation.
	
	Uses the toc information with msg_offset to pull out Status and
	Priority info, creates or alters appropriate headers with that info.
	"""
	global err

	re_between_angles = re.compile( '.*<(.*?)>.*' )
	re_before_parenth = re.compile( '(.*)\(.*?\)' )
	re_after_parenth = re.compile( '\(.*?\)(.*)' )

	hdr_line0 = headers.getValue( 'From ' )	# still has line end
	# Handle "Date: " and "From: " fields specially.
	# Keep the first encountered non-empty value in $hdr_date and
	# $hdr_from, thus ignoring subsequent Date:'s and From:'s, that
	# are, however, still added to @hdr_line in order to keep the
	# original (albeit malformed) message as intact as possible.
	# Use "Sender: " and "Return-Path: " as a backup for "From: ".
	# Try to extract a "Date:" unless we already have one.
	# Only keep them in @hdr_line, if they are not empty.
	# In other words, pop them away again, if there are empty.

	new_date = ""
	hdr_date = headers.getValue( 'Date:' )
	if not hdr_date:
		# Extract a date from Eudora's "From ???@??? " (with checks).
		""" r'\s*\S+?\s*(\S{3})\s+(\S{3})\s+(\d{1,2})\s+(\d{2}:\d{2}:\d{2})\s+(\d{4})' """
		date = re_from_date_time.match( hdr_line0 )

		if not date:
			msg = "Bad date in From '" + hdr_line0 + "'"
			log.record( msg, msg_no, line_no )
			err.record( msg, msg_no, line_no )
# DOES THIS ONLY HAPPEN IN EUDORA CASE?
#		new_date = 'Date: ' + d[0] + ' ' + d[2] + ' ' + d[1] + ' ' \
#						+ d[4] + ' ' + d[3]
		else:
			new_date = 'Date: ' + date.group(1) + ' ' \
				+ date.group(3) + ' ' + date.group(2) + ' ' \
				+ date.group(5) + ' ' + date.group(4)
			if date.group(6):
				new_date += ' ' + date.group(6)
		# This was 'warn', but it's by far the most common issue, and
		# it's not abnormal for Eudora.
			log.record( 'No  Date field, added    [' + new_date + ']', \
							msg_no, line_no )
			headers.add( 'Date:', new_date )

	hdr_date = headers.getValue( 'Date:' )
	fixed_date = fix_date( hdr_date )
	if fixed_date != hdr_date:
		headers.setValue( 'Date:', fixed_date )
	# Pine is picky about the contents of the Status header.  It will
	# ignore the whole thing if it doesn't understand the contents.
	# Basically, just keep R (read) and O (downloaded)
	hdr_status = headers.getValue( 'Status:' )
	if hdr_status:
		new_status = ''
		if hdr_status.find( 'R' ) != -1:
			new_status += 'R'
		if hdr_status.find( 'O' ) != -1:
			new_status += 'O'
		headers.setValue( 'Status:', new_status )
	# Set Pine's X-Status to A for answered if find another message
	# in this mailbox that is a reply to this message
	hdr_message_id = headers.getValue( 'Message-ID:' )
	if hdr_message_id and replies.message_was_answered( hdr_message_id ):
		hdr_x_status = headers.getValue( 'X-Status:' )
		if hdr_x_status:
			hdr_x_status += 'A'
		else:
			hdr_x_status = 'A'
		headers.setValue( 'X-Status:', hdr_x_status )
	# Try to extract a "From: " unless we already have one.
	# Only keep them in @hdr_line, if they are not empty.
	# In other words, pop them away again, if there are empty.

	# Determine sender's address from "From:" and fall back on
	# "Sender:" and "Return-Path:", respectively.
	new_from = headers.getValue( 'From:' )
	commented_from = headers.getValue( '>From:' )
	if not new_from:
		new_from = commented_from
	if hdr_line0.find( '???@???' ) > -1:
		if not new_from:
			if not new_from:
				new_from = headers.getValue( 'Send:' )
			if not new_from:
				new_from = headers.getValue( 'Return-Path:' )
			if not new_from:
				new_from = 'unknown@unknown.unknown'
				msg = 'No  From field, used   [' + new_from + ']'
				log.record( msg, msg_no, line_no )
				err.record( msg, msg_no, line_no )
			else:
				log.record( 'Had From field, used   [' \
					+ new_from + ']', msg_no, line_no )
		# Extract an e-mail address from $new_from with a _greedy_
		# match, if it matches on <...>, i.e. use the question mark (?)
		# in (.*?).  This ensures that after a "<", the first ">" will
		# be matched.
		# Especially Return-Path's can have multiple e-mail addresses.
		# If there are parentheses, the e-mail address is usually
		# outside it, so simply remove it.
		email_address = ''

		between_angles = re_between_angles.search( new_from, re.IGNORECASE )
		if between_angles:
			email_address = between_angles.group( 1 )
		else:
			before_parenth = re_before_parenth.search( new_from )
			if before_parenth:
				email_address = before_parenth.group( 1 )
			else:
				after_parenth = re_after_parenth.search( new_from )
				if after_parenth:
					email_address = after_parenth.group( 1 )
				else:
					email_address = new_from

		email_address = email_address.strip()
		log.record( 'e-mail address extracted <' + email_address + '>',
							msg_no, line_no )

		hdr_line0 = hdr_line0.replace( r'???@???', email_address, 1 )

		headers.setValue( 'From ', hdr_line0 )

	# Add a 'X-Eudora2Unix: ' header (if $emit_X_Eudora2Unix_Header is true)
	# This header is like (example: February 28, 2002 14:42:42 UTC+01:00):
	# 	X-Eudora2Unix: 2002-02-28T14:42:42+01:00 converted
	# and showed the date and time of conversion of this specific message.
	# It required GNU's date that supports the %Y and %z format specifier.
	# Alternatively, the Date::Manip perl package could be used, but this
	# is not always installed.
	# However, now the header has been changed to Zulu time (UTC +00:00),
	# using Perl's built-in 'gmtime(time)'.
	# This header is like (example: February 28, 2002 14:42:42 UTC+01:00):
	# 	X-Eudora2Unix: 2002-02-28T13:42:42Z converted
	# and showes the date and time of conversion of this specific message in
	# Zulu time (just like CVS). Note the one (1) hour difference in this
	# particular example.
	if emit_X_Eudora2Unix_Header == 1:
	# Begin of new time code with Perl's built-in gmtime(time).
	#
	# Get Zulu time with gmtime(time) and 'correct' month day (0..11)
	# and year (has 1900 substracted from it).
	# See also sub iso_8601_zulu(), provided for pleasure but not used
	# here, as again, a function call proved to perform worse by a factor
	# of 2 to 3 as compared to using the code directly.
		headers.add( 'X-Eudora2Unix:', iso_8601_zulu() + ' converted' )

	# Pull status and priority info out of the '.toc' file
	if toc:
		# SW: Careful here: the backtick integer-to-string translation
		# will put an 'L' at the end of the number, but we need the
		# decimal version for a textual lookup in the dictionary.
		offset_str = "%d" % ( msg_offset, )
		if toc.info_exists_for_msg_at( offset_str ):
			status_in_toc = toc.status_of_msg_at( offset_str )
			# See RFC 2076 for a discussion of Status header
			if status_in_toc:
				hdr_status = headers.getValue( 'Status:' )
				if hdr_status:
					hdr_status = status_in_toc + hdr_status
				else:
					hdr_status = status_in_toc
				headers.setValue( 'Status:', hdr_status )
			priority = int( toc.priority_of_msg_at( offset_str ) )
			if priority:
				# Kmail responds to this header
				headers.setValue( 'X-Priority:', "%d" % ( priority, ) )
				if priority > 0 and  priority < 3:
					# Pine responds to message 'flagged'
					# in X-Status (puts * in first column)
					hpri = headers.getValue( 'X-Status:' )
					if hpri:
						hpri += 'F'
					else:
						hpri = 'F'
					headers.setValue( 'X-Status:', hpri )
		else:
			warn.record( "No toc entry for message at offset "
					+ offset_str, msg_no, line_no )

	exceptions = [ 'Content-Type:'.lower(), ]
	# Now emit most of the headers.
	headers.emit( OUTPUT, exceptions )

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
	global err, warn, log
	global line_no
	if not mbx:
		fatal( P + ': usage: eudora2unix.pl eudora-mailbox-file.mbx' )
		return 0

	attachments = None
	target = ''
	if opts:
		for f, v in opts:
			if f == '-a':
				attachments = v
			if f == '-t':
				target = v

	msg_no	= 0	# number of messages in this mailbox
	line_no	= 0	# line number of current line record (for messages)

	headers = None
	last_file_position = 0
	msg_offset = 0

	re_initial_whitespace = re.compile( r'^[ \t]+(.*?)$' )

	err = ErrMessage( mbx )
	warn = WarnMessage( mbx )
	log = LogMessage( mbx )

	outfilename = mbx + OUT_SFX

	try:
		INPUT = open( mbx, 'r' )
	except IOError, ( errno, strerror ):
		INPUT = None
		return fatal( P + ': cannot open "' + mbx + '", ' + strerror )

	try:
		OUTPUT = open( outfilename, 'w' )
	except IOError, ( errno, strerror ):
		return fatal( P + ': cannot open "' + outfilename + '", ' 
						+ strerror )

	toc_info = TOC_Info( mbx )
	replies = Replies( INPUT )

	if verbose >= 0:
		print mbx + ':'

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
				err.record( 'Message start found inside message',
					msg_no, line_no )
				emit_headers( headers, toc_info,
					msg_offset, msg_no, replies, OUTPUT )
			else:
				#
				# Bingo, we're in a message.
				#
				pass

			msg_offset = last_file_position
			headers = Header()
			headers.add( 'From ', line[5:].strip() )
			msg_no += 1
		else:
			if headers:
				if re_initial_whitespace.match( line ):
					# Header "folding" (RFC 2822 3.2.3)
					headers.appendToLast( line )
				elif len( line.strip() ) == 0: 
					# End of message headers.
					emit_headers( headers, toc_info,
					msg_offset, msg_no, replies, OUTPUT )
					headers = None
					# Blank line separates headers and body
					# of message text
					print >> OUTPUT
				else:
					# Message header
					( id, value ) = parse_header( line )
					id = handle_duplicate( headers, id,
							msg_no, line_no )
					headers.add( id, value )
			else:
				if attachments and re_attachment.search( line ):
					handle_attachment( line, target, 
							attachments, OUTPUT,
							msg_no, line_no )
				else:
					# Message body, simply output the line.
					# Since it's not stripped, don't add 
					# line end
					print >> OUTPUT, strip_linesep( line )
				last_file_position = INPUT.tell()

	# Check if the file isn't empty and any messages have been processed.
	if line_no == 0:
		warn.record( 'empty file', msg_no, line_no )
	elif msg_no == 0:
		err.record( 'no messages (not a Eudora mailbox file?)',
			msg_no, line_no )

	# For debugging and comparison with a:
	#
	# 	'grep "^From ???@???" file.mbx | wc -l | awk '{ print $1 }'
	#
	#log_msg ("total number of message(s): $msg_no")
 
	if msg_no == 0: msg_str = '          no messages' 
	if msg_no == 1: msg_str = 'total:     1 message' 
	if msg_no >= 1: msg_str = 'total: %(msg_no)5d messages' % vars()

	warn_err_str = warn.summary() + ', ' + err.summary()

	if verbose >= 0:
		print '    ' + msg_str + '( ' + warn_err_str + ' )'

	# Finish up. Close failures usually indicate filesystem full.
	if INPUT:
		try:
			INPUT.close()
		except IOError:
			return fatal( P + ': cannot close "' + mbx + '"' )
	if OUTPUT:
		try:
			OUTPUT.close()
		except IOError:
			return fatal( P + ': cannot close "' + outfilename + '"' )
	del log
	del warn
	del err

	return 0

ok_to_dup = ( 'received:', 'x400-received:', 'delivered-to:', 'x-mailer:',
		'return-path:', 'sender:', 'mime-version:', 'precedence:',
		'x-uidl:', 'content-transfer-encoding:', )

def handle_duplicate( headers, id, msg_no, line_no ):
	""" Comment out most repeated headers, except a few that make sense to
	be repeated """
# Maybe better to specify headers that AREN'T OK to repeat:
# From From: To: Subject: Date: Message-Id:
	if( id and not id.lower() in ok_to_dup and headers.getValue( id ) ):
		warn.record( "extra '" + id +
			"' header encountered - commented out ",
			msg_no, line_no )
		return '>' + id
	else:
		return id

def handle_attachment( line, target, attachments, OUTPUT, msg_no, line_no ):
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
	attachments directory.  This has no direct effect in Kmail, but 
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
				+ attachment_desc + "\'" , msg_no, line_no )
	if len( name ) > 0:
		file = os.path.join( target, attachments, name )
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
