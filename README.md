Eudora2Unix
===========

Eudora2Unix is a collection of Python scripts that together convert
ancient Qualcomm Eudora mail folders to standard mailbox formats for
Unix or Linux.

These scripts are placed under the GNU General Public License and are
free software, both as in freedom and as in beer.

Note that the old Eudora mail folder format was radically inadequate
and varied between versions and platforms.

Reliable full conversion of Eudora mailboxes to mbox format is *not*
guaranteed.  These scripts will do a best effort attempt, but you
should be prepared to deal with some lossage.

The Scripts
-----------

## Eudora2Unix.py - Eudora mail folder tree walker
        
Main script that loops over the Eudora folders and calls the next
script, Eudora2Mbox.py, for each mailbox therein.
It then creates mailbox files / folders in any of several standard Linux/Unix formats.

## Eudora2Mbox.py - Eudora to unix mailbox converter
        
Converts a Eudora mailbox to any of several Linux/Unix mailbox
formats, fixing some header fields to allow for Eudora's
idiosyncracies, as well as those of Kmail and Pine.

You can also run the script directly on an individual mailbox or put
it in your own script that traverses the Eudora mail folder tree.
        
## EudoraTOC.py - Eudora toc file parser
        
Makes an educated guess as to the format of the proprietary Eudora
'.toc' files, prints out useful info as a text file.

This format is known to vary substantially between versions of Eudora,
and drastically between the Mac and Windows versions, so it is likely
not to work for untested Eudora versions.
        
## Header.py - Eudora Header parser
        
Handles parsing and cleanup / conversion of headers from Eudora MBX files.
        
## EudoraLog.py - Eudora2Unix Logging module

Handles notice / warn / error logging for the Eudora2Unix scripts.

## EudoraHTMLParser.py - HTML Parsing Module

An HTML parser instance used to determine content identifiers
(cid: URLs) in HTML messages to support MIME attachment of
embedded images in converted emails.
        
