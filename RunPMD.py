from collections import defaultdict, deque
from itertools import cycle
import os
import re
import subprocess
import tempfile
import threading
import time
import sublime, sublime_plugin



_TEMP_DIR = tempfile.mkdtemp()

ERROR = 'RunPMD.error'
WARNING = 'RunPMD.warning'
SETTINGS = sublime.load_settings("RunPMD.sublime-settings")

messagesForOutPane = []

FILL_STYLES = {
	'fill': sublime.DRAW_EMPTY,
	'outline': sublime.DRAW_OUTLINED,
	'none': sublime.HIDDEN
}

messagesByView = defaultdict(list)

problemsLock = threading.RLock()

def getMessage(view):
	messages = messagesByView[view.id()]
	messageRes = '';
	count = 1;
	existingMessages = [];
	for region, message in messages:
		if region.contains(view.sel()[0]) and message not in existingMessages :
			singleMsg = str(count)  + ')' + str(message,'UTF-8') 
			messageRes = messageRes + singleMsg;
			count+=1
			existingMessages.append(message)
	return messageRes	


class Edit:
	def __init__(self, view):
		self.view = view


	def __enter__(self):
		self.edit = self.view.begin_edit(self.view.id(),'cmd')
		#self.edit = self.view.begin_edit()
		return self.edit


	def __exit__(self, type, value, traceback):
		a = 1
		#self.view.end_edit(self.edit)


class SettingsError(Exception):
	pass


class Runner(threading.Thread):

	def __init__(self, view, settingGetter, results):
		threading.Thread.__init__(self)
		self.view = view
		self.getSetting = settingGetter
		self.results = results


class XLinter(Runner):
	"""The logic here was shamelessly ripped from SublimeLinter"""
	ERROR_RE = re.compile(r'^(?P<path>.*\.java):(?P<line>\d+): '
			+ r'(?P<warning>warning: )?(?:\[\w+\] )?(?P<error>.*)')
	MARK_RE = re.compile(r'^(?P<mark>\s*)\^$')
	END_RE = re.compile(r'[\d] error')

	def run(self):
		self.filename = self.view.file_name()
		path = ':'.join(self.getSetting('java_classpath') or ['.'])
		
		command = 'javac -g -Xlint -classpath {path} -d {temp} {fname}'.format(
				path = path, fname = self.filename, temp = _TEMP_DIR)

		p = subprocess.Popen(command, shell = True, stderr = subprocess.STDOUT,
				stdout = subprocess.PIPE)
		self._consumeXlintOutput(p)


	def _consumeXlintOutput(self, proc):
		problems = defaultdict(list)
		for line in proc.stdout:
			match = re.match(self.ERROR_RE, line)
			path = ''
			if match:
				path = os.path.abspath(match.group('path'))

				lineNumber = int(match.group('line'))
				warning = WARNING if match.group('warning') else ERROR
				message = match.group('error')

				# Skip forward until we find the marker
				position = -1

				while True:
					line = proc.stdout.next()
					match = re.match(self.MARK_RE, line)

					if match:
						position = len(match.group('mark'))
						break

				problems[path].append( dict(level = warning,
						message = message, sourceLineNumber = lineNumber,
						sourcePosition = position) )

			elif re.match(self.END_RE, line):
				continue
			elif path and problems[path]:
				problems[path][-1][message] += ('; ' + line.strip())


		for fname, lines in problems.items():
			with problemsLock:
				self.results[fname].extend(lines)
		

class PMDer(Runner):
	def _getPmdRulesets(self):
		rulesetPath = self.getSetting('ruleset_path')
		rules = self.getSetting('rules')
		if rulesetPath:
			return rulesetPath
		elif rules:
			return ','.join(r for r in rules)
		else:
			return sublime.packages_path() +'\\RunPMD\\'+'pmd-bin-5.5.0\\ruleset\\'+'complexity.xml,'+sublime.packages_path() +'\\RunPMD\\'+'pmd-bin-5.5.0\\ruleset\\'+'performance.xml,'+sublime.packages_path() +'\\RunPMD\\'+'pmd-bin-5.5.0\\ruleset\\'+'ruleset.xml'
			#return self._getPath('example.ruleset.xml')


	def _getPath(self, *args):
		return os.path.join(sublime.packages_path(), 'RunPMD', *args)


	def run(self):
		messagesByView = [];
		fname = self.view.file_name()
		rulesets = self._getPmdRulesets()
		#classpath = ':'.join([ self._getPath('pmd-bin-5.5.0', 'lib', f) 
		#		for f in os.listdir(self._getPath('pmd-bin-5.5.0', 'lib'))
		#		if f.endswith('.jar')])

		#cmd = [sublime.packages_path() +'\\RunPMD\\'+self.getSetting('pmd_version')+'\\bin\\'+ 'pmd.bat','-dir',fname,'-format','text','-R',rulesets]
		
		#rulesetsNew = sublime.packages_path() +'\\RunPMD\\'+'pmd-bin-5.5.0\\ruleset\\'+'complexity.xml,'+sublime.packages_path() +'\\RunPMD\\'+'pmd-bin-5.5.0\\ruleset\\'+'performance.xml,'+sublime.packages_path() +'\\RunPMD\\'+'pmd-bin-5.5.0\\ruleset\\'+'ruleset.xml'
						
		#cmd = [sublime.packages_path() +'\\RunPMD\\'+'pmd-bin-5.5.0'+'\\bin\\'+ 'pmd.bat','-dir',fname,'-format','text','-R',rulesetsNew]
		cmd = ['java','-classpath',sublime.packages_path() +'\\RunPMD\\'+'pmd-bin-5.5.0\\lib\*','net.sourceforge.pmd.PMD','-dir',fname,'-format','text','-R',rulesets]
		sub = subprocess.Popen(cmd,
				stdout = subprocess.PIPE, stderr = subprocess.STDOUT)
		self._consumePmdOutput(sub)


	def _consumePmdOutput(self, proc):
		print('*********** _consumePmdOutput **************')
		#del self.results[self.filename()]
		self.results.clear()
		print('start self.results')
		print( self.results)
		for line in proc.stdout:
			print(line)
			try:
				#fname = line.split(b':')[0]+line.split(b':')[1]
				fname = str(line.split(b':')[0],"UTF-8") + ':' + str(line.split(b':')[1],"UTF-8")
				line = line.split(b':')[2] + line.split(b':')[3]
				
				lineNumber, message = line.split(b'\t', 1)
				newLineNumber = str(lineNumber,"UTF-8")
				with problemsLock:
					self.results[fname].append( dict(level = WARNING, 
							sourceLineNumber = int(lineNumber),
							message = message.strip(),
							sourcePosition = 0) )
				
			except Exception as ValueError:
				print('******** ERROR ************* :')
				print(ValueError)
				print('******************************')
		print('final self.results')
		print( self.results)
	
class ExampleCommand(sublime_plugin.TextCommand):
	problems = defaultdict(deque)

	def run(self, edit):
		messagesForOutPane = []
		pmdObj = PMDer(self.view, self.getSetting, self.problems)
		pmdObj.run()	
		self._printProblems()

	def getSetting(self, name):
		settings = sublime.active_window().active_view().settings()
		if settings.has(name):
			return settings.get(name)
			
		if SETTINGS.has(name):
			return SETTINGS.get(name)

		return None

	def _printProblems(self):
		
		regions = defaultdict(list)
		while messagesByView[self.view.id()]:
			messagesByView[self.view.id()].pop(0)
		for filename, problems in sorted(self.problems.items(), 
				key = lambda x: x[0]):

			for problem in sorted(problems, 
					key = lambda x: x['sourceLineNumber']):
				point = self.view.text_point(problem['sourceLineNumber'] - 1, 
						problem['sourcePosition'] + 1)
				line = self.view.line(point)
				region = (line if problem['sourcePosition'] == 0 
						else self.view.word(point))
				problem['sourceLine'] = self.view.substr(line)

				if filename == self.view.file_name():
					messagesForOutPane.append(problem)

					messagesByView[self.view.id()].append( (region, 
							problem['message']) )
					regions[problem['level']].append(region)
				formattedMsg = self._formatMessage(problem)
				print('#'+formattedMsg)
		

		#if regions and self.getSetting('highlight'):
		if regions and True:
			#TODO mark = 'circle' if self.getSetting("gutter_marks") else ''
			mark = 'circle'
			#style = FILL_STYLES.get(
			#		self.getSetting('highlight_style'), 'outline')
			style = FILL_STYLES.get('outline', 'outline')
			for level, errs in regions.items():
				self.view.add_regions(level, errs, level, 
						mark, style)
				time.sleep(.100)
		
		
		if self.getSetting('results_pane') and False:
			out = self._getResultsPane('PMD Results')
			with Edit(out) as edit:
				out.replace(edit, sublime.Region(0, out.size()),
						self.view.file_name() + ":\n\n")
				outPaneMarks = defaultdict(list)
				for problem in messagesForOutPane:
					start = out.size()
					formattedMsg = self._formatMessage(problem)
					print('@'+formattedMsg)
					size = out.insert(edit, start, 
						   formattedMsg)
					out.run_command('append', {'characters': formattedMsg}) 
					out.run_command('append', {'characters': '\n'})
					outPaneMarks[problem['level']].append(
						sublime.Region(start + 1, start + 1 + size))

				for level, regions in outPaneMarks.items():
					out.add_regions(level, regions, level, 'dot',
						sublime.HIDDEN)
					time.sleep(0.1)


				if not messagesForOutPane:
					self._append(out, edit, '       -- pass -- ')


	def _formatMessage(self, problem): 
		line = problem['sourceLine']
		lineNumber = problem['sourceLineNumber']
		if len(line) > 80:
			line = line[:77] + '...'
		spacer1 = ' ' * (5 - len(str(lineNumber)))
		spacer2 = ' ' * (81 - len(line))
		
		#return '{sp1}{lineNumber}: {text}{sp2}{message}'.format(
		#		lineNumber = lineNumber, text = line, sp1 = spacer1,
		#		sp2 = spacer2, message = str(problem['message'],'UTF-8'))
		return '{sp1}{lineNumber}: {text}{sp2}{message}'.format(
				lineNumber = lineNumber, text = '', sp1 = spacer1,
				sp2 = '', message = str(problem['message'],'UTF-8'))


	def _raiseOutputPane(self, outputPane, basePane):
		if (basePane.window().active_view().id() == basePane.id()):
			self.window.focus_view(outputPane)
			self.window.focus_view(basePane)


	def _getResultsPane(self, name):
		resultsPane = [v for v in self.window.views() 
				if v.name() == name]
		if resultsPane:
			v = resultsPane[0]
			sublime.set_timeout(lambda: self._raiseOutputPane(v, self.view), 0)
			return v

		# otherwise, create a new view, and name it 'PMD Results'
		results = self.window.new_file()
		results.set_name(name)
		results.settings().set('syntax', os.path.join(
				'Packages', 'Default', 'Find Results.hidden-tmLanguage'))
		results.settings().set('rulers', [6, 86])
		results.settings().set('draw_indent_guides', False)
		results.set_scratch(True)
		return results


	def _append(self, view, edit, text, newline = True):
		def _actuallyAppend():
			view.insert(edit, view.size(), text)
			if newline:
				view.insert(edit, view.size(), '\n')
		sublime.set_timeout(_actuallyAppend, 0)
class SublimePMDBackground(sublime_plugin.EventListener):
    
    def on_post_save(self, view):
    	if(SETTINGS.get('do_pmd_on_save')):
    		view.run_command('example')

    def on_selection_modified(self, view):

        message = getMessage(view)
        if message:
            view.set_status('RunPMD-tip', message)
            view.show_popup(message,2,-1,600)
        else:
            #view.erase_status('sublimePMD-tip')
            view.set_status('RunPMD-tip', '')