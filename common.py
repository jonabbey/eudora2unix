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

