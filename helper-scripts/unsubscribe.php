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

$res = $db->prepare("DELETE FROM searches WHERE email=? AND id=? LIMIT 1");
$res->bind_param("si",$_REQUEST['e'],$_REQUEST['i']);
$res->execute();

if ($db->affected_rows > 0) {
	#success
	print "You will no longer receive emails about this.";
} else {
	#failure
	print "We weren't able to process your request.";
}

$db->close();

?>
