#!/bin/bash
#--------------------------------

# Web root
webrootdir="/var/django/quest/"

# Default TAR file base name
backup_basename='backup-quest-'
datestamp=`date +%d-%B-%Y_%H_%M_%S`

# Where the script is run from?  Do not run the script from a subdirectory
# of the $webroot
startdir='/var/django/backups/'
logfile=$startdir"/"$datestamp$backup_basename".log"

# Location to transfer tgz backup files to.
off_site_server_and_location=kevindunn@connectmv.com:teaching-backups/
off_site_ssh_port=22

# Exclusion list
#exclude_files=$startdir/'exclude-from-backups.txt'

# Web log file location
apache_logs=/var/log/apache2/

#----------
# No further configuration entries exist below this point
#----------

# Begin logging
echo "################################">>$logfile

# Clear the working folder ($startdir) from any previous *.tgz backups first
cd $startdir
rm *.tgz 2>>$logfile

tarname=$datestamp$backup_basename.tgz
echo "The script will backup files to: "$startdir/$tarname >> $logfile

# Copy the web log files over first
cd $webrootdir
rsync -av $apache_logs apache-logs >> $logfile

# TAR the directory
cd $webrootdir
wwwbackup_file=$startdir/$datestamp"-www-"$backup_basename".tgz"
echo "TARing ALL files from $webrootdir into $wwwbackup_file" >> $logfile
tar czf $wwwbackup_file . 2>>$logfile
#tar czf $wwwbackup_file -X $exclude_files . 2>>$logfile

# Copy the file to off-site location using scp
endtime=`date`
echo "$endtime : sending the tgz file to offsite location" >> $logfile
scp -P$off_site_ssh_port $wwwbackup_file $off_site_server_and_location

# Exit logging
endtime=`date`
echo "Backup completed $endtime" >> $logfile
echo "TAR file at $startdir/$tarname." >> $logfile

# Sending the logfile to offsite location
scp -P$off_site_ssh_port $logfile $off_site_server_and_location

