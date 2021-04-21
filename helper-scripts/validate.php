<?php
//ini_set ('error_reporting', E_ALL);
//ini_set ('display_errors', '1');
//error_reporting (E_ALL|E_STRICT);

include 'includes/mysql-vars.php';

if ( (!$_REQUEST['e']) || (!$_REQUEST['i']) ) {
	die("error\n");
} else {
	//print($_REQUEST['e']." ".$_REQUEST['i']);
}

$db = mysqli_init();
mysqli_options ($db, MYSQLI_OPT_SSL_VERIFY_SERVER_CERT, true);
$db->ssl_set('includes/client-key.pem', 'includes/client-cert.pem', 'includes/server-ca.pem', NULL, NULL);
$link = mysqli_real_connect ($db, $mysqlhost, $mysqluser, $mysqlpassword, $mysqldb, 3306, NULL, MYSQLI_CLIENT_SSL);
if (!$link) {
    die ('Connect error (' . mysqli_connect_errno() . '): ' . mysqli_connect_error() . "\n");
} 

$res = $db->prepare("UPDATE searches SET emailvalidated=1, validated=NOW() WHERE email=? AND id=? LIMIT 1");
$res->bind_param("si",$_REQUEST['e'],$_REQUEST['i']);
$res->execute();

if ($res->affected_rows > 0) {
	#success
	print "Thanks for validating your email address. You'll now receive notifications nightly.";
} else {
	#failure
	$res2=$db->prepare("SELECT * from searches WHERE email=? AND id=? LIMIT 1");
	if($res2->bind_param("si",$_REQUEST['e'],$_REQUEST['i'])) { } else { }
	$res2->execute();
	$res2->store_result();
	if ($res2->num_rows > 0) {
		print "Your email address had already been validated.";
	} else {
		print "We weren't able to validate your email address. You might want to create a new notification.";
	}
}

$db->close();

?>
