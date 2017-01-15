# -*- coding: utf-8 -*-

#Setup Logging
import logging
log = logging.getLogger(__name__)

#Python modules
import time

#Local modules
from ..alarm import Alarm
from ..utils import *
from telegram_stickers import stickerlist

#External modules
import telepot
import MySQLdb

global last_alert

last_alert = datetime.utcnow() - timedelta(minutes=30)
 
class Telegram_Alarm(Alarm):
 	
	_defaults = {
		'pokemon':{
			#'chat_id': If no default, required
			'title': "A wild <pkmn> has appeared!",
			'body': "Available until <24h_time> (<time_left>)."
		},
		'pokestop':{
			#'chat_id': If no default, required
			'title':"Someone has placed a lure on a Pokestop!",
			'body': "Lure will expire at <24h_time> (<time_left>)."
		},
		'gym':{
			#'chat_id': If no default, required
			'title':"A Team <old_team> gym has fallen!",
			'body': "It is now controlled by <new_team>."
		},
		'captcha': {
			# 'chat_id': If no default, required
			'title': 'dummy',
			'body': "<captcha_counter> Captcha müssen gelöst werden.\n \nKlicke hier um zu helfen:\nhttp://dapogo.de/go/captcha",
			'body_no_more_captcha': "Alle Captcha gel&ouml;st. Vielen Dank! &lt;3",
			'text_encounter': "Captcha Alarm!"
			# 'text_timeout': "Timeout waiting for captcha token for account <account>.",
			# 'text_solved': "Solved captcha for account <account>.",
			# 'text_failed': "Failed solving captcha for account <account>."
		}
	}
	
	#Gather settings and create alarm
	def __init__(self, settings):
		#Service Info
		self.bot_token = settings['bot_token']
		self.chat_id = settings.get('chat_id')
		self.venue = settings.get('venue', "False")
		self.location = settings.get('location', "True")
		self.disable_map_notification = settings.get('disable_map_notification', "True")
		self.startup_message = settings.get('startup_message', "True")
		self.startup_list = settings.get('startup_list', "True")
		self.stickers = parse_boolean(settings.get('stickers', 'True'))

		#Set Alerts
		self.pokemon = self.set_alert(settings.get('pokemon', {}), self._defaults['pokemon'])
		self.pokestop = self.set_alert(settings.get('pokestop', {}), self._defaults['pokestop'])
		self.gym = self.set_alert(settings.get('gym', {}), self._defaults['gym'])
		self.captcha = self.set_alert(settings.get('captcha', {}), self._defaults['captcha'])

		#Connect and send startup messages
 		self.connect()
		if parse_boolean(self.startup_message):
			self.client.sendMessage(self.pokemon['chat_id'], 'PokeAlarm activated! We will alert this chat about pokemon.')
		log.info("Telegram Alarm intialized.")

	#(Re)establishes Telegram connection
	def connect(self):
		self.client = telepot.Bot(self.bot_token) 
		
	#Set the appropriate settings for each alert
	def set_alert(self, settings, default):
		alert = {}
		alert.update(default)
		alert.update(settings)
		self.fix_boolean(alert)
		alert['chat_id'] = settings.get('chat_id', self.chat_id)
		alert['title'] = settings.get('title', default['title'])
		alert['body'] = settings.get('body', default['body'])
		alert['venue'] = parse_boolean(settings.get('venue', self.venue))
		alert['location'] = parse_boolean(settings.get('location', self.location))
		alert['disable_map_notification'] = parse_boolean(settings.get('disable_map_notification', self.disable_map_notification))
		alert['stickers'] = parse_boolean(settings.get('stickers', self.stickers))
		return alert
 		
	def fix_boolean(self, alert):
		for key, value in alert.iteritems():
			b = parse_boolean(value)
			if b != None:
				alert[key] = b

	#Send Alert to Telegram
 	def send_alert(self, alert, info, sticker_id=None):
		if sticker_id:
			stickerargs = {
 				'chat_id': alert['chat_id'],
				'sticker': sticker_id,
 				'disable_notification': 'True'
 				}
			try_sending(log, self.connect, 'Telegram', self.client.sendSticker, stickerargs)
			
		if alert['venue']:
			args = { 
				'chat_id': alert['chat_id'],
				'latitude': info['lat'],
				'longitude':  info['lng'],
				'title': replace(alert['title'], info) ,
				'address': replace(alert['body'], info),
				'disable_notification': 'False'
			}
			try_sending(log, self.connect, "Telegram (Loc)", self.client.sendVenue, args)
		else:
			args = {
				'chat_id': alert['chat_id'],
				'text': '<b>' + replace(alert['title'], info) + '</b> \n' + replace(alert['body'], info),
				'parse_mode': 'HTML',
				'disable_web_page_preview': 'False',
				'disable_notification': 'False'
			}
			try_sending(log, self.connect, "Telegram", self.client.sendMessage, args)
		if alert['location']:
  			args = { 
  				'chat_id': alert['chat_id'],
  				'latitude': info['lat'],
  				'longitude':  info['lng'],
  				'disable_notification': "%s" % alert['disable_map_notification']
  			}
			try_sending(log, self.connect, "Telegram (Loc)", self.client.sendLocation, args)

	# Trigger an alert based on Captcha notification
	def captcha_alert(self, captcha_info):
		global last_alert
		
		if last_alert <= (datetime.utcnow() - timedelta(minutes=20)):
			# Open database connection
			db = MySQLdb.connect("dapogo.de","kevin","minikeks09","speed" )

			# prepare a cursor object using cursor() method
			cursor = db.cursor()

			# query using execute() method.
			cursor.execute("SELECT * FROM captcha WHERE token_needed=1")

			captcha_counter = cursor.rowcount

			# if captcha_info['status'] == 'encounter':
			# 	captcha_counter = captcha_increase()
			# else:
			# 	captcha_counter = captcha_decrease()

			if captcha_counter > 20 and captcha_info['status'] == 'encounter':
				# get notification message and return if it is not set
				text = self.captcha['text_' + captcha_info['status']]
				if not text:
					return

				# customize alert, overwrite text, disable location and venue
				alert = {}
				alert.update(self.captcha)
				alert['title'] = text
				alert['location'] = False
				alert['venue'] = False
				if captcha_counter == 0:
					alert['body'] = self.captcha['body_no_more_captcha']

				# provide global captcha counter
				captcha_info['captcha_counter'] = captcha_counter

				last_alert = datetime.utcnow()

				self.send_alert(alert, captcha_info)

	#Trigger an alert based on Pokemon info
	def pokemon_alert(self, pokemon_info):
		if self.pokemon['stickers']:
			self.send_alert(self.pokemon, pokemon_info, stickerlist.get(pokemon_info['id']))
		else:
			self.send_alert(self.pokemon, pokemon_info)
		
		
	#Trigger an alert based on Pokestop info
	def pokestop_alert(self, pokestop_info):
		if self.pokestop['stickers']:
			self.send_alert(self.pokestop, pokestop_info, stickerlist.get('pokestop'))
		else:
			self.send_alert(self.pokestop, pokestop_info)
		
	#Trigger an alert based on Pokestop info
	def gym_alert(self, gym_info):
		if self.gym['stickers']:
			self.send_alert(self.gym, gym_info, stickerlist.get(gym_info['new_team'].lower()))
		else:
			self.send_alert(self.gym, gym_info)
