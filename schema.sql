CREATE TABLE `searches` (
  `id` mediumint(9) NOT NULL AUTO_INCREMENT,
  `email` varchar(255) DEFAULT NULL,
  `created` datetime DEFAULT NULL,
  `validated` datetime DEFAULT NULL,
  `searchphrase` varchar(255) DEFAULT NULL,
  `emailvalidated` tinyint(1) DEFAULT NULL,
  PRIMARY KEY (`id`)
) ENGINE=InnoDB AUTO_INCREMENT=9 DEFAULT CHARSET=utf8

CREATE TABLE `notifications` (
  `id` mediumint(9) NOT NULL,
  `title` varchar(255) DEFAULT NULL,
  `reference` varchar(255) NOT NULL,
  `meetingdate` varchar(255) DEFAULT NULL,
  `decisionBodyName` varchar(255) DEFAULT NULL,
  `email` varchar(255) DEFAULT NULL,
  `emailsent` char(1) DEFAULT '0',
  PRIMARY KEY (`id`,`reference`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8

