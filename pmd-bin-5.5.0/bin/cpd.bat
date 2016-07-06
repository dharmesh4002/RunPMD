@echo off
set TOPDIR=%~dp0
set OPTS=
set MAIN_CLASS=net.sourceforge.pmd.cpd.CPD

java -classpath %PMD_HOME%\lib\* %OPTS% %MAIN_CLASS% %*
