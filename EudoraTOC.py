#!/usr/bin/env python

"""
For interpreting Eudora mailbox '.toc' files.

Structure elements are read as characters because integers are all
big-endian (like the Mac), and I want this to run on little-ending
machines (like the IBM PC).

This code could be much improved by making use of Python's built-
in endian struct declarations

Note that some Mac versions keep the toc info in the resource forks
of the mailbox files.  This info has to be put in a toc file before
this script can work.  A utilitiy for doing this is available at
<ftp://ftp.eudora.com/eudora/eudoralight/mac/extras/utils/TOCConvert.sea.hqx>

For Windows Eudora TOC file format, see
http://wso.williams.edu/~eudora/kens/toc.html
Note the Mac and Windows formats are quite different

See RFC 2076 for a discussion of Status header
"""
__author__ = "Stevan White <Stevan_White@hotmail.com>"
__date__ = "2003-03-06"
__version__ = "1.3"
import sys
import re
import string
from struct import *

if sys.hexversion < 33686000:
	sys.stderr.write( "Aborted: Python version must be at least 2.2.1" \
		+ os.linesep )
	sys.exit( 1 )

# Eudora Status field (Mac 3.1 version): 1 = '*', 2 = ' ', 4 = 'D', 8 = 'F'
# IN case of 8, interpretation is 'F' when incoming, 'S' when outgoing
# displayed in first column of the mailbox window
# 	'*' means unread or unsent, is marked with big dot.
# 	' ' means read or sent, is otherwise blank
# 	'D' means redirected
# 	'F' means forwarded
# others, I don't know how they're encoded
# 	'Q' means queued
# 	'S' means sent
# 	'-' means never sent

# There are regions of the TOC structure that seem to change every time
# the file is written.  Some of these are in areas that are in the space
# for a null-terminated string.  This suggests that the structure is read
# piecewise into uninitialized memory.  An obstacle for reverse-engineering.

mac_folder = string.join( (
	'2s',	# version, always 0x0001
	'42x',	# 
	'14x',	# 
	'B',	# name len
	'45s',	# name	('mailbox names must be 27 characters or less')
	'174x',	# 	(to make total 278)
	), '' )

win_folder = string.join( (
	'2s',	# version, 0x3000 for Pro 5, 0x2a00 for Lite 1.x
	'6x',	# 
	'32s',	# name
	'2x',	# type,	int 0 - In, 1 - Out, 2 - Trash,  3 - User
	'2x',	# 
	'2x',	# int class 0 - User, 1 - System
	'8x',	# window size
	'2x',	# col_S_width
	'2x',	# col_P_width
	'2x',	# col_A_width
	'2x',	# col_Label_width	 (Pro only)
	'2x',	# col_Who_width
	'2x',	# col_Date_width
	'2x',	# col_K_width
	'2x',	# col_V_width
	'2x',	# 	(all 0)
	'30x',	# 	(all 0)
	'2x',	# n_mess
	), '' )
	
# Other info that must be stored here: 
# Signature on/off, Word Wrap on/off, Keep Copy on/off,
# Text Attachment in Body on/off
# Quoted Printable on/off
#
# Mime/Binhex, Attachment present 

mac_entry = string.join( (
	'4s',	# offset to message in corresponding mailbox
	'4s',	# length of message in corresponding mailbox
	'4x',	# offset to body of message
	'B',	# status ... & 1 = U, & 2 = R, & 4 = & 8 = S
	'x',	# Date length
	'32s',	# Date (0-terminated?)
	'6x',	# 
	'x',	# misc: "bla" or "full headers" if value is 8
	'x',	# 
	'8x',	# window size
	'B',	# priority unset = 0; Hi MedHi Norm MedLo Lo = 40 80 120 160 200
	'x',	# 
	'14x',	# 	(shorts?)
	'B',	# To length
	'46s',	# To - truncated to 46 bytes
	'16x',	# 
	'x',	# 
	'B',	# Subject length
	'58s',	# Subject - truncated to 58 bytes
	'18x',	# 
	'x',	#
), '' )

win_entry = string.join( (
	'4s',	# offset to message in corresponding mailbox
	'4s',	# length of message in corresponding mailbox
	'xxxx',	# GMT
	'B',	# status (only the first bytes seem to be status)
	'x',	#	(disagree with interp on above web page)
	'2x',	# switches
	'B',	# priority
	'x',	# 
	'32s',	# Date (0-terminated?)
	'64s',	# To
	'64s',	# Subject
	'8x',	# window size
	'2x',	# 
	'4x',	# 
	'26x',	# 	(all 0)
), '' )

# Eudora toc file versions I've seen:
# MAC_EUDORA_LITE_3 = 0x0001
# MAC_EUDORA_LITE_131 = 0x0000 # (a Poor choice!)
# WIN_EUDORA_LITE_1 = 0x2a00
# WIN_EUDORA_5 = 0x0300

# Just a guess: maybe Mac and Windows are distinguished thus (with 0 being Mac)
def isMac( version ):
	MAC = 0x00FF
	return version & MAC or version == 0

def isWin( version ):
	WIN = 0xFF00
	return version & WIN

# Big-Endian integer conversions

def toIntBig( c ):
	i = unpack( '4B', c )
	return i[0] << 24 | i[1] << 16 | i[2] << 8 | i[3]

def toShortBig( c ):
	i = unpack( 'BB', c )
	return i[0] << 8 | i[1]

def toIntLittle( c ):
	i = unpack( '4B', c )
	return i[3] << 24 | i[2] << 16 | i[1] << 8 | i[0]

def toShortLittle( c ):
	i = unpack( 'BB', c )
	return i[1] << 8 | i[0]

def unpackstr( str, i = 0 ):
	""" got from comp.lang.python Michael P. Reilly 1999/05/14 """
	if not str:
		return None
	for c in str:
		if c == '\000':
			break
		i = i + 1
	return str[:i]

def printMacFolder( out, folder ):
	( version, nlen, name ) = unpack( mac_folder, folder )
	print >> out, "Eudora Mac TOC version 0x%x" % ( toShortBig( version ), )
	print >> out, "Folder:  %.*s" % ( nlen, name, )
	print >> out, ""

def printWinFolder( out, folder ):
	( version, name ) = unpack( win_folder, folder )
	print >> out, "Eudora Windows TOC version 0x%x" % ( toShortLittle( version ), )
	print >> out, "Folder:  " +  unpackstr( name )
	print >> out, ""

def printMacEntry( out, entry ):
	( offset, length, status, date, priority, to_len, to,
			subject_len, subject ) = unpack( mac_entry, entry )
	print >> out, "offset:   %d" % ( toIntBig( offset ), )
	print >> out, "length:   %d" % ( toIntBig( length ), )

	print >> out, "status:  ",
	if status == 0xa:	# unsent 
		pass
	if status == 0x9:	# sent 
		print >> out, "OR",
	if status == 0x1:	# popped, unread 
		print >> out, "O",
	if status == 0x2:	# popped, read 
		print >> out, "OR",
	if status == 0x3:	# popped, replied 
		print >> out, "OR",
	if status == 0x4:	# popped, redirected 
		print >> out, "OR",
	if status == 0x8:	# popped, forwarded 
		print >> out, "OR",

	print >> out
	print >> out, "valueofstatus: 0x%x" % ( status, )
# can't decide on this.  in some mailboxes, entry.date_length seems to
# contain a necessary truncation of a junk date string, in others,
# it is 0 
#	printf( "Date:    %.*s", entry.date_length, entry.Date );
	print >> out, "Date:     %s" % ( unpackstr( date ), )
	print >> out, "To:       %.*s" % ( to_len, to, )
	print >> out, "Subject:  %.*s" % ( subject_len, subject, )
	print >> out, "priority: %d" % ( priority / 40, )
	print >> out

def printWinEntry( out, entry ):
	( offset, length, status, priority, date, to, subject ) \
					= unpack( win_entry, entry )
	print >> out, "offset:   %d" % ( toIntLittle( offset ), )
	print >> out, "length:   %d" % ( toIntLittle( length ), )

	print >> out, "status:  ", 

	if status == 0x1:	# popped, unread 
		print >> out, "O",
	if status == 0x2:	# popped, replied 
		print >> out, "OR",
	if status == 0x3:	# popped, forwarded 
		print >> out, "OR",
	if status == 0x4:	# popped, redirected 
		print >> out, "OR",
	if status == 0x5:	# toc rebuilt 
		print >> out, "",
	if status == 0x6:	# saved 
		print >> out, "",
	if status == 0x7:	# queued 
		print >> out, "",
	if status == 0x8:	# sent 
		print >> out, "",
	if status == 0x9:	# unsent 
		print >> out, "",
	if status == 0xa:	# time queued 
		pass
	print >> out
	print >> out, "valueofstatus: 0x%x" %( status, )
# can't decide on this.  in some mailboxes, entry.date_length seems to
# contain a necessary truncation of a junk date string, in others, it is 0 
#	printf( "Date:    %.*s", entry.date_length, entry.Date );
	print >> out, "Date:     %s" % ( unpackstr( date ), )
	print >> out, "To:       %s" % ( unpackstr( to ), )
	print >> out, "Subject:  %s" % ( unpackstr( subject ), )
	print >> out, "priority: %d" % ( priority, )
	print >> out

def readVersionAndRewind( file ):
	verbuf = file.read( 2 )
	v = unpack( 'BB', verbuf )

	file.seek( 0 )

	if len( verbuf ) > 0:
		return ( v[0] << 8 ) | v[1]

	return 0

class TOCError(Exception):
	""" Problem occurred concerning a Eudora TOC file.  """
	def __init__(self, value):
		self.args = value
	def __str__(self):
		return `self.args`
	def args(self):
		return self.args

def parse( infile, outfile = None ):
	"""
	Parse a Eudora '.toc' file, and pull out important info into  a text 
	file '.toc.txt' 

	Determines whether the toc file is from Mac or Windows based on the
	version found int he first two bytes of the file.

	This version number seems to be made to look good in hex, but not
	doesn't really mean much as an integer.   For example,
	Mac Eudora Lite 3.x has version 0001, Windows Eudora Pro 5.o has 0030
	As a guess, if the upper byte is nonzero, it's Windows, otherwise,
	it's Mac.
	"""
	file = None
	returnVal = 0
	out = sys.stdout

	try:
		file = open( infile, "rb" )
	except IOError, ( errno, strerror ):
		raise TOCError( "EudoraTOC: couldn't open file " + infile )

	if outfile:
		print 'Writing %s' % outfile
		try:
			out = open( outfile, "w" )
		except IOError, ( errno, strerror ):
			raise TOCError( "EudoraTOC: couldn't open file "
						+ outfile )
	version = readVersionAndRewind( file )
	
	if isMac( version ):
		foldersize = calcsize( mac_folder )
		entrysize = calcsize( mac_entry )
	elif isWin( version ):
		foldersize = calcsize( win_folder );
		entrysize = calcsize( win_entry );
	else:
		raise TOCError( "EudoraTOC: unknown toc version: 0x%x" \
						% version )
	print >> out, "Expect folder and entry sizes %d %d" \
						% ( foldersize, entrysize )
	folder = file.read( foldersize )

	if len( folder ) == 0:
		raise TOCError( "EudoraTOC: couldn't read header" )

	if isMac( version ):
		printMacFolder( out, folder )
	elif isWin( version ):
		printWinFolder( out, folder )

	while True:
		entry = file.read( entrysize )

		if len( entry ) <= 0:
			break

		if isMac( version ):
			printMacEntry( out, entry )
		elif isWin( version ):
			printWinEntry( out, entry )

	if file:
		file.close()

	return returnVal

if sys.argv[0].find( 'EudoraTOC.py' ) > -1:	# i.e. if script called directly
	if len( sys.argv ) < 2:
		raise TOCError( "EudoraTOC: insufficient arguments" )
	if len( sys.argv ) >= 3:
		outfile = sys.argv[2]
	else:
		outfile = None
	try:
		sys.exit( parse( sys.argv[1], outfile ) )
	except TOCError, errstr:
		print errstr
		sys.exit( 1 )
