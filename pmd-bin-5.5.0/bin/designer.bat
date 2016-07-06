@echo off
set TOPDIR=%~dp0
set OPTS=
set MAIN_CLASS=net.sourceforge.pmd.util.designer.Designer

java -classpath "%PMD_HOME%\lib\*" %OPTS% %MAIN_CLASS% %*
