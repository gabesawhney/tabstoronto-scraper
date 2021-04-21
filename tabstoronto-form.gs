/*
Tabs Toronto
google apps script to get data from Google Forms into mysql. Also sends validation email
*/

var mysqluser = 'MYSQLUSER';
var mysqluserPwd = 'MYSQLUSERPWD';
var mysqlhost = 'MYSQLHOST'
var mysqldb = 'MYSQLDB'

var dbUrl = 'jdbc:mysql://' + mysqlhost + ':3306/' + mysqldb;

function onSubmit(e) {
  var frm = FormApp.getActiveForm().getItems();
 
  var searchphrase = e.response.getResponseForItem(frm[0]).getResponse();
  var email = e.response.getResponseForItem(frm[1]).getResponse();

  var conn = Jdbc.getConnection(dbUrl, {user: mysqluser, password: mysqluserPwd});
  var stmt = conn.prepareStatement('INSERT INTO searches (searchphrase, email, created) values (?, ?, NOW())',1);
  stmt.setString(1, searchphrase);
  stmt.setString(2, email);
  stmt.execute();

  var results = stmt.getGeneratedKeys();
  while (results.next()) {
    var id = results.getInt(1);
  }

  var emailbody = "Hey, we think you just signed up to be notified when we find new agenda items in TMMIS matching '" + searchphrase + "'. To confirm that you want to receive these notifications, please click this link: http://pwd.ca/tabs/validate.php?e="+encodeURIComponent(email)+"&i="+id+"\n\nIf you didn't request this notification, please ignore this email."
  MailApp.sendEmail (email, "New Tabs search: " + searchphrase, emailbody);
}
