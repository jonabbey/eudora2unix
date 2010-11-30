#!/usr/bin/env python
"""
Classes for handling Eudora Mailbox header parsing and clean up.
"""

import os
import re
import time
import string
import EudoraLog

# Configuration.

# Add a 'X-Eudora2Unix: <ISO 8601 date> converted' header at the end
# of the emitted headers (see sub emit_headers),  0=no, 1=yes.
# This can come in handy later to differentiate between 'new' KMail
# messages and those inherited from the conversion.

emit_X_Eudora2Unix_Header = 1

# End of configuration.

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

date_pat = r'\s*\S+?\s*(\S{3})\s+(\S{3})\s+(\d{1,2})'
time_pat = r'\s*(\d{2}:\d{2}:\d{2})\s+(\d{4})\s*([+-]\d{4}){0,1}'
re_from_date_time = re.compile( date_pat + time_pat )
re_message_start = re.compile( r'^From' + date_pat + time_pat )
re_timeout_protection = re.compile( r'^X-(NortonAV|Symantec)-TimeoutProtection' )

def strip_linesep( line ):
	"""Regular expressions proved too slow, and rstrip doesn't take
        an argument in my distribution (?)"""
        while len( line ) > 0 and ( line[-1] == '\n' or line[-1] == '\r' ):
		line = line[0:-1]
        return line

# SW
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
			if EudoraLog.verbose >= 0:
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


# SW
class Header:
	"""
	A list of mailbox headers.
	Implements case-insensitive searching (RFC 561 explicitly states
	case of headers is undefined); keeps a mixed-case version for output.

	A dictionary doesn't work for this because several header
	lines can share the same key, e.g. 'Received:'.

	Three fields used:
		lowercase-id, id, value

	The first is for searching by id, the second is to make id
	output like the input.
	"""

        ok_to_dup = ( 'received:', 'x400-received:', 'delivered-to:', 'x-mailer:',
                      'return-path:', 'sender:', 'mime-version:', 'precedence:',
                      'x-uidl:', 'content-transfer-encoding:', )

	def __init__( self ):
		self.data = []
		self.index = 0
                self.cleaned = False
	
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
		if self.getValue( id ):
			lcid = id.lower()
			for h in self.data:
				if h[0] == lcid:
					h[2] = self.stripOffID( id, value )
					break
		else:
			self.add( id, value )

	def removeValue( self, id ):
		newlist = []
		lcid = id.lower()
		for h in self.data:
			if h[0] != lcid:
				newlist.append(h)
		self.data = newlist

	def replaceValue( self, id, value ):
		self.removeValue(id)
		self.add(id, value)

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

        def add_line(self, line):
            """Parses a header line into a (key, value) tuple, trimming
            whitespace off ends.  Introductory 'From ' header not treated."""

            colon = line.find( ':' )
            space = line.find( ' ' )

            # If starts with something with no whitespace then a colon,
            # that's the From ID, and we won't handle it here

            if colon == -1 or ( space != -1 and space <= colon ):
                return

            id = line[ 0: colon + 1 ]
            value = line[ colon + 1:]
            if value:
                value = value.strip()

            # Comment out most repeated headers, except a few that
            # make sense to be repeated

	    if ( re_timeout_protection.match( line ) ):
		    return

            if( id and not id.lower() in Header.ok_to_dup and self.getValue( id ) ):
                EudoraLog.log.warn( "extra '" + id +
                                    "' header encountered - commented out ")
                id = '>' + id

            self.add( id, value )

        def clean(self, toc, msg_offset, replies):
            """
            Processes headers from a Eudora mbx message.  Data is taken
            from the Header object passed in as 'headers', the TOC_Info
            object passed as 'toc', and the Replies object passed as
            'replies'.

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

            The modified headers are left in the headers param, which is
            also returned as the return value from this function.
            """
            if self.cleaned:
		    print "Hey, already cleaned!"
		    return

            re_between_angles = re.compile( '.*<(.*?)>.*' )
            re_before_parenth = re.compile( '(.*)\(.*?\)' )
            re_after_parenth = re.compile( '\(.*?\)(.*)' )

            hdr_line0 = self.getValue( 'From ' )	# still has line end

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
            hdr_date = self.getValue( 'Date:' )
            if not hdr_date:
                    # Extract a date from Eudora's "From ???@??? " (with checks).
                    """ r'\s*\S+?\s*(\S{3})\s+(\S{3})\s+(\d{1,2})\s+(\d{2}:\d{2}:\d{2})\s+(\d{4})' """
                    date = re_from_date_time.match( hdr_line0 )

                    if not date:
                            msg = "Bad date in From '" + hdr_line0 + "'"
                            EudoraLog.log.log( msg )
                            EudoraLog.log.error( msg )
                    else:
                            new_date = 'Date: ' + date.group(1) + ' ' \
                                    + date.group(3) + ' ' + date.group(2) + ' ' \
                                    + date.group(5) + ' ' + date.group(4)
                            if date.group(6):
                                    new_date += ' ' + date.group(6)
                    # This was 'warn', but it's by far the most common issue, and
                    # it's not abnormal for Eudora.
                            EudoraLog.log.log( 'No  Date field, added    [' + new_date + ']')
                            self.add( 'Date:', new_date )

            hdr_date = self.getValue( 'Date:' )
            fixed_date = fix_date( hdr_date )
            if fixed_date != hdr_date:
                    self.setValue( 'Date:', fixed_date )
            # Pine is picky about the contents of the Status header.  It will
            # ignore the whole thing if it doesn't understand the contents.
            # Basically, just keep R (read) and O (downloaded)
            hdr_status = self.getValue( 'Status:' )
            if hdr_status:
                    new_status = ''
                    if hdr_status.find( 'R' ) != -1:
                            new_status += 'R'
                    if hdr_status.find( 'O' ) != -1:
                            new_status += 'O'
                    self.setValue( 'Status:', new_status )
            # Set Pine's X-Status to A for answered if find another message
            # in this mailbox that is a reply to this message
            hdr_message_id = self.getValue( 'Message-ID:' )
            if hdr_message_id and replies.message_was_answered( hdr_message_id ):
                    hdr_x_status = self.getValue( 'X-Status:' )
                    if hdr_x_status:
                            hdr_x_status += 'A'
                    else:
                            hdr_x_status = 'A'
                    self.setValue( 'X-Status:', hdr_x_status )
            # Try to extract a "From: " unless we already have one.
            # Only keep them in @hdr_line, if they are not empty.
            # In other words, pop them away again, if there are empty.

            # Determine sender's address from "From:" and fall back on
            # "Sender:" and "Return-Path:", respectively.
            new_from = self.getValue( 'From:' )
            commented_from = self.getValue( '>From:' )
            if not new_from:
                    new_from = commented_from
            if hdr_line0.find( '???@???' ) > -1:
                    if not new_from:
                            if not new_from:
                                    new_from = self.getValue( 'Send:' )
                            if not new_from:
                                    new_from = self.getValue( 'Return-Path:' )
                            if not new_from:
                                    new_from = 'unknown@unknown.unknown'
                                    msg = 'No  From field, used   [' + new_from + ']'
                                    EudoraLog.log.log( msg )
                                    EudoraLog.log.error( msg )
                            else:
                                    EudoraLog.log.log( 'Had From field, used   [' + new_from + ']')

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
#                    EudoraLog.log.log( 'e-mail address extracted <' + email_address + '>')

                    hdr_line0 = hdr_line0.replace( r'???@???', email_address, 1 )

                    self.replaceValue( 'From ', hdr_line0 )

            # Add a 'X-Eudora2Unix: ' header (if $emit_X_Eudora2Unix_Header is true)
            # This header is like (example: February 28, 2002 14:42:42 UTC+01:00):
            # 	X-Eudora2Unix: 2002-02-28T14:42:42+01:00 converted
            # and showed the date and time of conversion of this specific message.
            # This header is like (example: February 28, 2002 14:42:42 UTC+01:00):
            # 	X-Eudora2Unix: 2002-02-28T13:42:42Z converted
            # and showes the date and time of conversion of this specific message in
            # Zulu time (just like CVS). Note the one (1) hour difference in this
            # particular example.

            if emit_X_Eudora2Unix_Header == 1:
                    # Get Zulu time with gmtime(time) and 'correct' month day (0..11)
                    # and year (has 1900 substracted from it).
                    # See also sub iso_8601_zulu(), provided for pleasure but not used
                    # here, as again, a function call proved to perform worse by a factor
                    # of 2 to 3 as compared to using the code directly.
                    self.add( 'X-Eudora2Unix:', iso_8601_zulu() + ' converted' )

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
                                    hdr_status = self.getValue( 'Status:' )
                                    if hdr_status:
                                            hdr_status = status_in_toc + hdr_status
                                    else:
                                            hdr_status = status_in_toc
                                    self.setValue( 'Status:', hdr_status )
                            priority = int( toc.priority_of_msg_at( offset_str ) )
                            if priority:
                                    # Kmail responds to this header
                                    self.setValue( 'X-Priority:', "%d" % ( priority, ) )
                                    if priority > 0 and  priority < 3:
                                            # Pine responds to message 'flagged'
                                            # in X-Status (puts * in first column)
                                            hpri = self.getValue( 'X-Status:' )
                                            if hpri:
                                                    hpri += 'F'
                                            else:
                                                    hpri = 'F'
                                            self.setValue( 'X-Status:', hpri )
                    else:
                            EudoraLog.log.warn( "No toc entry for message at offset " + offset_str)

            self.cleaned = True
