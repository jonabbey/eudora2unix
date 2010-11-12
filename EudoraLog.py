import os

# Verbosity.
# Determines if subroutines {log,warn,err}_msg send output to stdout, too:
#
#     verbose = -1  # ultra quiet: not even the mailbox's message total
#     verbose =  0  # really quiet
#     verbose =  1  # errors only
#     verbose =  2  # warnings and errors only
#     verbose =  3  # logging, warnings and errors
#
verbose = 3

log = None
msg_no = 0
line_no = 0

LOG_SFX = '.E2U_LOG'
ERR_SFX = '.E2U_ERR'
WARN_SFX = '.E2U_WARN'

def fatal(msg):
	if msg and len( msg ) > 0:
		print >> sys.stderr, msg
	return 1


# SW
class Log:
	"""A log dedicated to a specific Eudora2Mbox mail box that we
	are converting.  Records messages in it (depending on
	verbosity, also prints on stdout), summarizes messages
	recorded, and closes file."""

	total_msgs = 0
	exit_code = 0


	def __init__(self, mbx):
		self.mbxname = mbx
		self.log_msgs = 0
		self.warn_msgs = 0
		self.error_msgs = 0
		
	def record(self, filename, msg, verbosity):
		global P, verbose
		msg += os.linesep
		out = self.mbxname + ' (msg #' + `msg_no` + ', line #' \
		    + `line_no` + '):' + os.linesep + msg

		if verbose >= verbosity:
			print out

		try:
			OUT = open( filename, 'a' )
			OUT.write( out + os.linesep )
			OUT.flush()
		except IOError, ( errno, strerror ):
			return fatal( P + ': cannot open "' 
				      + filename + '"' + ": " + strerror )
		finally:
			if OUT:
				OUT.close()

		Log.total_msgs += 1

	def _summary(self, n_msgs, logtype):
		if n_msgs == 0: return 'no ' + logtype + ' messages'
		if n_msgs == 1: return '1 ' + logtype + ' message'
		if n_msgs >= 1: return `self.log_msgs` + logtype + ' messages'

	def summary(self):
		return self._summary(self.log_msgs, 'log') + os.linesep + \
		    self._summary(self.warn_msgs, 'warning') + os.linesep + \
		    self._summary(self.error_msgs, 'error') + os.linesep

	def log(self, msg):
		self.record(self.mbxname + LOG_SFX, msg, 1)
		self.log_msgs += 1

	def warn(self, msg):
		self.record(self.mbxname + WARN_SFX, msg, 2)
		self.warn_msgs += 1
		Log.exit_code = 1

	def error(self, msg):
		self.record(self.mbxname + ERR_SFX, msg, 3)
		self.error_msgs += 1
		Log.exit_code = 1
