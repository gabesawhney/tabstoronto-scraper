<?php
/*
ini_set ('error_reporting', E_ALL);
ini_set ('display_errors', '1');
error_reporting (E_ALL|E_STRICT);
*/

include 'includes/mysql-vars.php';

$db = mysqli_init();
mysqli_options ($db, MYSQLI_OPT_SSL_VERIFY_SERVER_CERT, true);
$db->ssl_set('includes/client-key.pem', 'includes/client-cert.pem', 'includes/server-ca.pem', NULL, NULL);
$link = mysqli_real_connect ($db, $mysqlhost, $mysqluser, $mysqlpassword, $mysqldb, 3306, NULL, MYSQLI_CLIENT_SSL);
if (!$link) {
    die ('Connect error (' . mysqli_connect_errno() . '): ' . mysqli_connect_error() . "\n");
} 



#delete notifications where the meetingdate <= yesterday
	# save affected_rows to past_notifications

$res=$db->prepare("SELECT id from notifications WHERE meetingdate < NOW() - INTERVAL 30 DAY");
$res->execute();
$res->store_result();
$older_notifications = $res->num_rows;
if ($older_notifications > 0) {
	#ok, delete the notifications we just found
	$res3=$db->prepare("DELETE from notifications WHERE meetingdate < NOW() - INTERVAL 30 DAY");
	$res3->execute();
	$res3->store_result();
	$deleted_notifications = $res3->affected_rows;

	#now let's find the number of previously deleted notifications
	$res2=$db->prepare("SELECT number from stats WHERE name='past_notifications' ORDER BY date desc LIMIT 1");
	$res2->execute();
	$res2->bind_result($previously_deleted_notifications);
	$res2->fetch();
	$res2->free_result();

	#now let's record the total number of deleted records
	$total_deleted = $deleted_notifications + $previously_deleted_notifications;
	if ($res4=$db->prepare("INSERT INTO stats (name, number) VALUES('past_notifications',?)")) {
		$res4->bind_param('i',$total_deleted);
		$res4->execute();
	} else {
		$error = $db->errno . ' ' . $db->error;
	    echo $error;
	}
} else {
	#print "Nothing to delete";
	$deleted_notifications = 0;	

	#now let's find the number of previously deleted notifications
	$res5=$db->prepare("SELECT number from stats WHERE name='past_notifications' ORDER BY date desc LIMIT 1");
	$res5->execute();
	$res5->bind_result($previously_deleted_notifications);
	$res5->fetch();
	$res5->free_result();

}

#now let's pull the number of records which haven't been deleted
$res6=$db->prepare("SELECT id from notifications");
$res6->execute();
$res6->store_result();
$recent_notifications = $res6->num_rows;

#now let's pull the number of unique email addresses
$res7=$db->prepare("SELECT COUNT(DISTINCT email) FROM `searches`");
$res7->execute();
$res7->bind_result($unique_emails);
$res7->fetch();
$res7->free_result();

#now let's pull the number of searches
$res9=$db->prepare("SELECT COUNT(id) FROM `searches`");
$res9->execute();
$res9->bind_result($num_searches);
$res9->fetch();
$res9->free_result();

/*
print "Previously deleted notifications: ".$previously_deleted_notifications."<br/>";
print "Currently deleted notifications: ".$deleted_notifications."<br/>";
print "Notifications still in the table: ".$recent_notifications."<br/>";
print "Total notifications (".$previously_deleted_notifications." + ".$deleted_notifications." + ".$recent_notifications.") =  ";
print $previously_deleted_notifications + $deleted_notifications + $recent_notifications;
*/

$stats = new stdClass(); 
$stats->notif_total = $previously_deleted_notifications + $deleted_notifications + $recent_notifications;
$stats->unique_users = $unique_emails;
$stats->num_searches = $num_searches;

$stats_json = json_encode($stats);
file_put_contents("stats.json",$stats_json);

//var_dump($stats);


#delete searches where created <= a week ago, if emailvalidated isn't 1
$res8=$db->prepare("DELETE FROM searches WHERE emailvalidated IS NULL AND created < NOW() - INTERVAL 14 DAY");
$res8->execute();
$res8->store_result();
$deleted_searches = $res8->affected_rows;

$db->close();

?>
