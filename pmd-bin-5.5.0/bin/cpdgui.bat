@echo off
set TOPDIR=%~dp0..
set OPTS=
set MAIN_CLASS=net.sourceforge.pmd.cpd.GUI
echo 'PMD Home'
echo %PMD_HOME%
java -classpath "%PMD_HOME%\lib\*" %OPTS% %MAIN_CLASS% %*
