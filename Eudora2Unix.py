#!/usr/bin/env python
"""
Walk through a Eudora mail directory converting mailboxes to unix .mbox format,
for either pine or kmail
"""
__author__ = "Stevan White <Stevan_White@hotmail.com"
__credits__ = "Based on Eudora2Unix.sh by Eric Maryniak"
__date__ = "2003-04-29"
__version__ = "1.3"
import sys
import types
import time
import shutil
import os
from os.path import *
import re
import string
import getopt

if sys.hexversion < 33686000:
	sys.stderr.write( "Aborted: Python version must be at least 2.2.1" \
		+ os.linesep )
	sys.exit( 1 )

import Eudora2Mbox
import EudoraTOC

OUT_SFX = '.E2U_OUT'
ORIG_SFX = '.E2U_ORIG'
re_mbx_sfx = re.compile( '(.*?)\.mbx$', re.IGNORECASE )
re_toc_sfx = re.compile( '(.*?)\.toc$', re.IGNORECASE )
re_fol_sfx = re.compile( '(.*?)\.fol$', re.IGNORECASE )
re_out_sfx = re.compile( '(.*?)\.e2p_out$', re.IGNORECASE )
re_in = re.compile( 'in\.mbx', re.IGNORECASE )
re_out = re.compile( 'out\.mbx', re.IGNORECASE )
re_trash = re.compile( 'trash\.mbx', re.IGNORECASE )
isMac = False;	# global for convert_files
# --------------------- Comments & complaints ----------------------
def usage_complaint( arg ):
	return [
	'Usage error; specify Eudora directory to be converted:',
	'   ' + arg + ' [-a attachments directory] [-d target directory] eudora_directory [kmail|pine]'
	]

def target_directory_already_exists_complaint( maildir ):
	return [
	'Directory ' + maildir + ' already exits.  Rename it, e.g. to ',
	maildir + '-old',
	'then you can merge the old into the new mail directory',
	'(' + maildir + ') after conversion.'
	]

def source_directory_not_readable_complaint( src ):
	return '"' + src + '" is not a (readable) directory, abort.' 

def not_eudora_directory_complaint():
	return 'This is not a Eudora directory; cannot find inbox, abort.' 

def entered_directory_remark( DIR ):
	return 'Entered directory ' + DIR

def entering_directory_complaint( DIR, strerror ):
	return "Cannot enter directory '" + DIR + "': " + strerror + ', abort.'

def cannot_open_complaint( fpath, strerror ):
	return 'Cannot open "' + fpath + '"' + ": " + strerror

def cannot_move_complaint( src, dst, strerror ):
	return "Cannot move '" + src + "' to '" + dst + "' : " + strerror

def cannot_copy_complaint( f, dst, strerror ):
	return "Cannot copy '" + f + "' to '" + dst + f + "' : " + strerror 

def copying_directory_message( src, dest ):
	return 'Copying directory ' + src + ' to ' + dest

def finished_copying_directory_message( src, dest ):
	return 'Finished copying directory ' + src + ' to ' + dest

def user_specific_script_message( user_pre_script ):
	return [
	'Pre-actions with script', 
	'    ' + user_pre_script + 'started.'
	]
def user_specific_script_success():
	return 'finished successfully.'

def user_specific_script_complaint( strerror ):
	return [
	'Finished UNsuccessfully.',
	'User-defined script failed. Abort.',
	strerror
	]

def ciao_remark():
	return [
	'Ok, see you later, alligator ;-)',
	''
	]

def initial_warning( eudor_directory ):
	return [
	'Quote:',
	'', 
	'  Beware of bugs in the above code;', 
	'  I have only proved it correct, not tried it.', 
	'', 
	'      - Donald Knuth', 
	'', 
	'', 
	'Ok, the Eudora mailbox converter is about to start.', 
	'In principle, the Eudora directory should be left unchanged...', 
	'But just in case, are you sure you have made a backup copy of the', 
	'Eudora directory:', 
	'    ' + eudor_directory, 
	'',
	]

def user_made_backup_prompt():
	return 'I have made a backup copy [y/N]: '

def last_chance_to_bail_remark():
	return [ 
	"Right, let's rock.", 
	'Expect lots of output... which is OK.', 
	'', 
	'Last chance to bail out.' 
	]
def last_chance_prompt():
	return 'Hit return to continue, control-C to stop: '

def starting_remark():
	return [
	'',
	'Starting.'
	]

def copying_special_mailboxes_remarks( maildir ):
	return 'Copying Eudora mailboxes (In, Out, Trash) to ' + maildir

def beginning_conversion_remarks( maildir ):
	return [ 
	'',
	'',
	'Beginning conversion of files in ' + maildir
	]

def moving_converted_remarks( maildir ):
	return 'Moving converted files to original names in ' + maildir 

def toc_complaint( f_toc, strerror ):
	return "cannot analyse toc file '" + f_toc  + "' : " + strerror

def fixing_permissions_remarks( maildir ):
	return [ 
	'',
	'Fixing file permissions in ' + maildir 
	]

def aux_file_removal_remarks():
	return [ 
	'', 
	'DONE.', 
	'', 
	'Use the following command to analyze conversion problems:',
	'', 
	'  (', 
	'    cd $HOME/Mail && for f in `find . -type f -print | sort`; do', 
	'        [ -f $f.E2U_WARN ] && diff -u $f.E2U_ORIG $f', 
	'        [ -f $f.E2U_ERR  ] && diff -u $f.E2U_ORIG $f', 
	'    inform', 
	'    done', 
	' , \ | less -eiMs +/\"^\\@\\@\"', 
	'', 
	'You should first convert all *.E2U_ORIG files from DOS to Unix',
	"EOL (End-Of-Line) convention, or else you will get lots of diff's.", 
	"Example:  dos2unix \`find \$HOME/Mail -name '*.E2U_ORIG' -print\`",
	'', 
	'After analysis, remove these files with:', 
	'', 
	'  find $HOME/Mail -type f \\', 
	"  ( -name '*.E2U_*' -o -name '*.toc*' -o ) -exec rm -v '{}' ';'", 
	'', 
	'You will also want to remove any directories or files that',
	'do not correspond directly to mail folders or mailboxes,',
	'or to the attachments directory.',
	'', 
	]

def windows_concluding_remarks():
	return [
	"Windows Eudora has a file 'dscmap.pci' in each subdirectory.",
	'Eudora2Unix uses these files, but you may delete them after ',
	'conversion.',
	'', 
	]

def concluding_remarks( target, targetdir ):
	return [
	"When you're satisfied, move " + targetdir + ".e2u to " + targetdir, 
	'and fire up ' + target +'.  Good luck!', 
	'', 
	]
#
# Help functions and aliases.
#
def complain( message ):
	if message:
		if isinstance( message, types.ListType ):
			for line in message[:]:
				complain( line )
		else:
			sys.stderr.write( basename( sys.argv[0] ) + '! ' \
                                                        + message + os.linesep )

def inform( message ):
	if message:
		if isinstance( message, types.ListType ):
			for line in message[:]:
				inform( line )
		else:
			print basename( sys.argv[0] ) + ': ' + message 

def exit_msg( msg, maildir = None ):
	complaint = [ 
	'A fatal error occurred:', 
	'   ' + msg, 
	]
	if maildir:
		complaint.append(
		[ 'Aborting; directory ' + maildir + ' (if present)', 
		'probably has an inconsistent state and should be removed.', ] )
	complain( complaint )
	sys.exit( 1 )

def eudoaralike( d, isMac ):
	if( isMac or re_fol_sfx.match( d ) or re_mbx_sfx.match( d ) ):
		looksLikeEudora = 1

def convert_directory( eudoradir, opts ):
	"""
	GNU/Linux or Unix Mail directory and Eudora directory (arg 1).
	Remove a trailing slash (eudoradir/ -> eudoradir) in the latter.
	Enforce the Eudora directory to be an absolute path (below).
	Relative paths (such as '.') will give problems, because this script
	does a few cd's (change directory) and must therefore be able to come
	back where it came from.
	"""
	global isMac

	target = 'pine'
	targetdir = ''
	for f, v in opts:
		if f == '-t':
			target = v.strip().lower()
	for f, v in opts:
		if f == '-d':
			targetdir = v.strip()
	if targetdir == '':
		if( target == 'kmail' ):
			targetdir = 'Mail'
		else:
			targetdir = 'mail' # works for pine
		opts.append( ( '-t', targetdir ) )
	maildir = join( os.environ['HOME'], targetdir + '.e2u' )
	maildirLENGTH = len( maildir )

	eudoradir = abspath( eudoradir )

	if isdir( maildir ):
		complain( target_directory_already_exists_complaint( maildir ) )
		sys.exit( 1 )

	if not os.access( eudoradir, os.R_OK ):
		complain( source_directory_not_readable_complaint( eudoradir ) )
		sys.exit( 1 )

	try:
		os.chdir( eudoradir )
		inform( entered_directory_remark( eudoradir ) )
	except OSError, ( errno, strerror ):
		exit_msg( entering_directory_complaint( eudoradir, strerror ),
			maildir)
		sys.exit( 1 )

	isMac = isfile( 'In' )

	if( not isMac and not isfile( 'In.mbx' )
			and not isfile( 'in.mbx' )
			and not isfile( 'IN.mbx' )
			and not isfile( 'IN.MBX' ) ):
		complain( not_eudora_directory_complaint() )
		sys.exit( 1 )
	#
	# Let's rock.
	#
	inform( initial_warning( eudoradir ) )

	line = raw_input( user_made_backup_prompt() ).lower().strip()
	if line != 'y':
		inform( ciao_remark() )
		sys.exit( 0 )
	else:
		inform( last_chance_to_bail_remark() )
		raw_input( last_chance_prompt() )
		inform( starting_remark() )
		time.sleep( 1 )
		inform( '' )

	inform( copying_directory_message( eudoradir, maildir ) )
	shutil.copytree( eudoradir, maildir )
	inform( finished_copying_directory_message( eudoradir, maildir ) )

	# runs ~/bin/eudora2unix-file-renames.sh

	execute_user_pre_script( 'bin/eudora2unix-file-renames.sh', maildir )

	move_special_mailboxes( target, maildir, isMac )

	inform( beginning_conversion_remarks( maildir ) )
	walk( maildir, convert_files, opts )

	inform( moving_converted_remarks( maildir ) )
	if target == 'pine':
		to_pine( maildir, isMac )
	elif target == 'kmail':
		to_kmail( maildir, isMac )

	inform( fixing_permissions_remarks( maildir ) )
	walk( maildir, fix_file_permissions, 0 )

	# Hasta la vista, baby.
	inform( aux_file_removal_remarks() )
	if not isMac:
		inform( windows_concluding_remarks() )
	inform( concluding_remarks( target, targetdir ) )
	sys.exit( 0 )

def execute_user_pre_script( local_script_path, maildir ):
	""" User-specific pre-actions first.  Add your hook here.
	Note: script exit code is checked and must be 0, to continue. """
	
	user_pre_script = join( os.environ['HOME'], local_script_path )

	if isfile( user_pre_script ):
		inform( user_specific_script_message( user_pre_script ) )
		try:
			os.system( user_pre_script )
			inform( user_specific_script_success() )
		except OSError, ( errno, strerror ):
			complain( user_specific_script_complaint( strerror ) )
			rmdir( maildir )
			sys.exit( 1 )

def move_special_mailboxes( target, maildir, isMac ):
	"""
	Copy In, Out and Trash box.
	Skip 'drafts' and touch 'outbox'.
	Name conversions:
	---------       -----------------     ----------------
	Eudora *   -->  Pine                  KMail
	---------       -----------------     ----------------
	In.mbx          saved-messages **     inbox
	Out.mbx         sent-mail             sent-mail
	Trash.mbx       ***                   trash
	n/a             postponed-msgs        outbox (touched)
	n/a                                   drafts (skipped)
	---------       -----------------     ----------------
	*   Eudora for the Mac lacks the .mbx suffix
	**  When used as a POP client, Pine's INBOX is on the server; not a
	    real file; downloaded messages are in saved-messages
	*** Pine doesn't have a trash mailbox--just marks messages for
	    deletion.
	"""
	if isMac:
		mailbox_suffix = ''
	else:
		mailbox_suffix = '.mbx'
	inTarget = ''
	outTarget = ''
	trashTarget = ''
	if target == 'pine':
		inTarget = 'saved-messages'
		outTarget = 'sent-mail'
		trashTarget = 'trash'
	if target == 'kmail':
		inTarget = 'inbox'
		outTarget = 'sent-mail'
		trashTarget = 'trash'
		
	try:
		os.chdir( maildir )
	except OSError, ( errno, strerror ):
		exit_msg( entering_directory_complaint( maildir, strerror ),
			maildir)

	inform( copying_special_mailboxes_remarks( maildir ) )

	move_special_mbox( maildir, inTarget, mailbox_suffix, 
	[ 'In', 'In.mbx', 'in.mbx', 'IN.mbx', 'IN.MBX' ] )

	move_special_mbox( maildir, outTarget, mailbox_suffix, 
	[ 'Out', 'Out.mbx', 'out.mbx', 'OUT.mbx', 'OUT.MBX' ] )

	move_special_mbox( maildir, trashTarget, mailbox_suffix, 
	[ 'Trash', 'Trash.mbx', 'trash.mbx', 'TRASH.mbx', 'TRASH.MBX' ] )

def move_special_mbox( dir, targetname, suffix, namelist ):
	for f in namelist:
		fpath = join( dir, f )
		if isfile( fpath ):
			f_nombx = re_mbx_sfx.sub( '\\1', fpath )
			t_nombx = join( dir, targetname )
			t_mbx = t_nombx + suffix
			moveFile( fpath, t_mbx )
			f_toc = f_nombx + '.toc'
			t_toc = t_nombx + '.toc'
			if isfile( f_toc ):
				moveFile( f_toc, t_toc )

def convert_files( avoid_dirlist, dir, names ):
	"""
	Copy Eudora folders in the top level Eudora directory recursively.
	Only copy the mailbox files in those folders.
	In the next step, the subfolders and mailboxes will be processed.

	Typical Eudora Win directory has lots of files that arent mailboxes
	and folders that don't contain mail
	For Eudora 5.0, 
	All mail subfolders are in Subfolders.fol/
	Then there's attach/ which contains attachments.
	Then the standard mailboxes
		In.mbx In.toc Out.mbx Out.toc Test.mbx Test.toc
		Trash.mbx Trash.toc
	In each directory, there's a database
		descmap.pce
	that associates DOS filenames with Eudora Mailbox names in Win 3.1,
	and associates filenames with .mbx suffix with Mailbox names in other
	versions of Windows.
	Besides that, we have
		Filters/        NNdbase.toc     Audit.log    History.lst
		NNdbase.txt     icons/          DoNotDel.tmp 
		Embedded/       Plugins/   
		eudora.ini      LinkHistory/    RCPdbase.txt uchange.tlx
		eudora.log      LinkHistory.dat Sigs/        uignore.tlx
		EudoraStats.xml lmos.dat        spool/       usuggest.tlx
		EudPriv/        Nickname/       Stationery/

	SW THIS ASSUMES eudoradir DOESN"T END IN SLASH

	Process all Eudora mailbox files with the per-mailbox
	converter 'Eudora2Mbox.py'.
	Rename the Eudora mailbox file to .E2U_ORIG (backup copy).
	Move the converted mailbox, e.g. 'myproj.E2U_OUT', to 'myproj' which
	will be the unix mbox.
	Analyze by diffing with (e.g. diff-ing against the .E2U_ORIG version).
	"""
	# avoid any directory specified with a '-a' flag
	for f, v in opts:
		if f == '-a' and samefile( dir, v ):
			return
	descmap = parse_descmap( dir )
	for f in names:
		fpath = join( dir, f )
		f_targ = join( dir, get_eudora_boxname( f, descmap, isMac ) );
		if( isfile( fpath ) and ( isMac or re_mbx_sfx.match( f ) ) 
					and not re_toc_sfx.match( f ) ):
			f_nombx = re_mbx_sfx.sub( '\\1', fpath )
			f_out = f_nombx + OUT_SFX 
			f_orig = f_nombx + ORIG_SFX 
			f_toc = f_nombx + '.toc'
			if exists( f_toc ):
				try:
#					os.spawnlpe( os.P_WAIT, 'etoc', 'etoc',
#						f_toc, f_toc + '.txt',
#						os.environ )
					EudoraTOC.parse( f_toc, f_toc + '.txt' )
				except OSError, ( errno, str ):
					complain( toc_complaint( f_toc, str ) )
			moveFile( fpath, f_nombx )
			Eudora2Mbox.convert( f_nombx, opts )
			moveFile( f_nombx, f_orig )
			moveFile( f_nombx + OUT_SFX, f_targ )
			print

def parse_descmap( dir ):
	"""Eudora Windows mailbox folders have associated 'descmap.pce' file,
	which associates a Eudora mailbox name with a Windows filename.  In
	Windows 95+, the filename just has a '.mbx' added to the mailbox name.
	In Windows 3.2-, the filename is 8 characters with '.mbx' suffix.
	It has been known to happen that a Windows mailbox name contained
	a slash, so such slashes are replaced by Unix-friendly underscores."""
	nameMap = {}
	fpath = join( dir, 'descmap.pce' )
	if isfile( fpath ):
		try:
			dscfile = open( fpath, 'r' )
			for line in dscfile:
				desc_toc = line.split( ',' )
				nameMap[desc_toc[1]] = string.replace(
						desc_toc[0], "/", "_" )
		except IOError, ( errno, strerror ):
			complain( cannot_open_complaint( fpath, strerror ) )
	return nameMap

def get_eudora_boxname( f, nameMap, isMac ):
	if not isMac and nameMap:
		try:
			return nameMap[f]
		except KeyError:
			pass
	return re_mbx_sfx.sub( '\\1', f )

def moveFile( src, dst ):
	try:
		os.rename( src, dst )
	except OSError, ( errno, strerror ):
		exit_msg( cannot_move_complaint( src, dst, strerror ) )
# We now have all Eudora mailboxes (*.mbx with .mbx extension removed)
# properly processed in Eudora folders (*.fol).

re_fol_suffix = re.compile( '(.*?)\.fol$', re.IGNORECASE )

def to_kmail( d, isMac ):
	"""
	KMail handles folders and subfolders specially.
	For a mail folder 'foobar', KMail uses a file 'foobar' and directory
	'.foobar.directory' (note the dot) which is the actual container
	of the folder contents, as well as a folder named 'foobar'
	containing subdirectories 'cur', 'new', and 'tmp'.
	"""
	descmap = parse_descmap( d )
	dirlist = os.listdir( d )
	for f in dirlist:
		fpath = join( d, f )
		if isdir( fpath ) and ( isMac or re_fol_sfx.match( fpath ) ):
			boxname = get_eudora_boxname( f, descmap, isMac )
			f_targ = '.' + boxname + '.directory'
			f_targ = join( d, f_targ )
			to_kmail( fpath, isMac )
			moveFile( fpath, f_targ ) # rename on way back up
			print "in to_kmail" , fpath, f_targ
			box = join( d, boxname )
			os.mkdir( box )
			os.mkdir( join( box, 'cur' ) )
			os.mkdir( join( box, 'new' ) )
			os.mkdir( join( box, 'tmp' ) )

def to_pine( d, isMac ):
	"""Removes '.fol' suffix from Eudora Windows folders"""
	if isMac:
		return;
	descmap = parse_descmap( d )
	dirlist = os.listdir( d )
	for f in dirlist:
		fpath = join( d, f )
		if isdir( fpath ) and re_fol_sfx.match( fpath ):
			f_targ = get_eudora_boxname( f, descmap, isMac )
			f_targ = join( d, f_targ )
			to_pine( fpath, isMac )
			moveFile( fpath, f_targ ) # rename on way back up

def fix_file_permissions( arg, dir, names ):
	"""Fix permissions (your eyes only). """
	for f in names:
		fpath = join( dir, f )
		if isfile( fpath ):
			os.chmod( fpath, 0600 )
		elif isdir( f ):
			os.chmod( fpath, 0700 )

# --------------------- START HERE --------------------------------
# Note: in this rather stupid implementation of getopts, has to go
# program flags args, or else
try:
	opts, args = getopt.getopt( sys.argv[1:], 'a:d:t:' )
except getopt.GetoptError:
	complain( usage_complaint( sys.argv[0] ) )
	sys.exit( 1 )

if len( args ) < 1 or len( args[0].strip() ) == 0:
	complain( usage_complaint( sys.argv[0] ) )
	sys.exit( 1 )
else:
	eudoradir = args[0].strip()
	convert_directory( eudoradir, opts )
