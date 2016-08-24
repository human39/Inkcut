#!/usr/bin/env python
# -*- coding: utf-8 -*-
#
#	  name.py
#-----------------------------------------------------------------------
#	  Copyright 2010 Jairus Martin <frmdstryr@gmail.com>
#	  
#	  This program is free software; you can redistribute it and/or modify
#	  it under the terms of the GNU General Public License as published by
#	  the Free Software Foundation; either version 2 of the License, or
#	  (at your option) any later version.
#	  
#	  This program is distributed in the hope that it will be useful,
#	  but WITHOUT ANY WARRANTY; without even the implied warranty of
#	  MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#	  GNU General Public License for more details.
#	  
#	  You should have received a copy of the GNU General Public License
#	  along with this program; if not, write to the Free Software
#	  Foundation, Inc., 51 Franklin Street, Fifth Floor, Boston,
#	  MA 02110-1301, USA.
#-----------------------------------------------------------------------
#

import pygtk,sys,os,logging, math
pygtk.require('2.0')
import gtk
from lxml import etree
import bin.path as hpgl
import bin.material as material
import bin.preview as preview
from bin.settings import Settings
from bin.device import Device
import subprocess

appPath = os.path.dirname(__file__)
LOG_FILENAME = os.path.join(appPath,'tmp','log')

units = {'in':90.0, 'pt':1.25, 'px':1, 'mm':3.5433070866, 'cm':35.433070866, 'm':3543.3070866,'km':3543307.0866, 'pc':15.0, 'yd':3240 , 'ft':1080}


class Application(object):
	def __init__(self, svg, nodes,inkex):
		logging.basicConfig(level=logging.DEBUG,
			format='%(asctime)s %(levelname)s %(message)s',
			filename=LOG_FILENAME,
			filemode='w')
		#-----------------------format input--------------------
		self.svg = svg.getroot()
		self.inkex = inkex
		
		def getSelectedById(IDlist): # returns lxml elements that have an id in IDlist in the svg
			ele=[]
			for e in self.svg.iterfind('.//*[@id]'):
				if e.get('id') in IDlist:
					ele.append(e)
			return ele
		
		self.nodes = getSelectedById(nodes)
		logging.info("Selected elements: %s"%(self.nodes))
		
		
		#-----------------------start building gui--------------------
		builder = gtk.Builder()
		glade = os.path.join(appPath,"gui","inkcut.glade")
		builder.add_from_file(glade)
		glade = etree.parse(glade)
		self.set_adjustment_values(builder,glade)
		self.populate_combos(builder)
		
		#-----------------------saved widgets-------------------- 
		widgets = ['offset','overcut','smoothness','textviewlog','preview1','preview2','pathh','pathw',
			'material','material-length','material-width','velocity','force','feed','scale','copies','posnx','posny',
			'spacing-row','spacing-col','margin','tile-col','tile-row','weed_box','weed_v_box','weed_h_box',
			'overcut-box','offset-box','cutter-box','file-box','feeding1','feeding2','invert-box','rotate-box','filechooserbutton1',
			'plotdata','plotdetails','inkscape_preview','order_box','order_combo','color_cut_combo','Yax',
			'edt_1x','edt_1y','edt_2x','edt_2y','edt_home_x','edt_home_y','chk_1x10','chk_2x10','cmb_plotlang',
			'device-length','device-width',
			'calibration','interface','printer','port','baudrate','parity','device1',
			'bytesize','stopbits','xonxoff','rtscts',
			'dsrdtr']
		self.gui = {}
		for widget in widgets:
			self.gui[widget] = builder.get_object(widget)

		#-----------------------load settings --------------------
		self.settings = Settings(os.path.join(appPath,'config','settings.xml'),self.gui)
		self.settings.load('last')
		self.gui['edt_home_x'].set_text('0')
		self.gui['edt_home_y'].set_text('0')

		#-----------------------Create Graphic & Initialize Plot --------------------
		self.plot = hpgl.Plot( {'rotate':self.calculate_degree() } )
		self.plot.loadGraphic( self.nodes, self.gui['color_cut_combo'].get_active_text() )

		self.on_color_cut_changed(self.gui['color_cut_combo'])		
		self.on_material_size_changed()
		self.on_pos_value_changed()
		self.on_spacing_value_changed()
		self.on_margin_value_changed()
		self.on_velocity_value_changed()
		self.on_force_value_changed()
		self.on_feeding_group_changed()
		self.on_invertbox_toggled(None)
		self.on_smoothness_value_changed()
		self.on_overcut_value_changed()
		self.on_offset_value_changed()
		self.on_weed_h_box_toggled(self.gui['weed_h_box'])
		self.on_weed_v_box_toggled(self.gui['weed_v_box'])
		self.on_weed_box_toggled(self.gui['weed_box'])
		self.on_order_changed(self.gui['order_box'])
		self.on_reset_stack_btn_clicked(self.gui['copies'])
		self.on_order_changed(self.gui['order_combo'])
		self.on_calibration_value_changed(self.gui['calibration'])
		self.set_device_combo(builder.get_object("device1"))
		
		# do this last...
		self.on_preview_clicked('first')
		#-----------------------show windows--------------------
		self.window	= builder.get_object( "window1" )
		self.about_dialog = builder.get_object( "aboutdialog1" )
		self.properties_dialog  = builder.get_object( "dialog1" )
		self.log_dialog  = builder.get_object( "dialog2" )
		self.plot_dialog  = builder.get_object( "dialog3" )
		self.concut_dialog  = builder.get_object( "concutdlg" )

		builder.connect_signals(self)
	
	def set_adjustment_values(self,builder,etree): # fix defaults not loading
		for object in etree.xpath('/interface/object[@class="GtkAdjustment"]'):
			property = object.xpath('property[@name="value"]')
			if len(property):
				obj = builder.get_object(object.get('id'))
				obj.set_value(float(property[0].text))

	def set_device_combo(self, combo):		
		#LW2013: which port or printer has the output? Write to device_combo
		device = str( self.get_combobox_active_text(self.gui['interface']).lower() )
		if device == 'serial':
			device += ': ' + str(self.get_combobox_active_text(self.gui['port'])) + ' : ' + str(self.get_combobox_active_text(self.gui['baudrate']))
		else:
			device += ': ' + str(self.get_combobox_active_text(self.gui['printer']))
		combo.clear()		
		self.set_model_from_list(combo,[device])
		combo.set_active(0)


   
	# ------------ combobox population & functions ------------------
	
	def populate_combos(self,builder): # populate combo boxes
		# interfaces
		combo = builder.get_object("interface")
		self.set_model_from_list(combo,['Printer','Serial'])
		combo.set_active(1)
		
		# printer options
		import cups
		con = cups.Connection()
		printers = con.getPrinters()
		combo = builder.get_object("printer")
		self.set_model_from_list(combo,printers)
		combo.set_active(len(printers)-1)

		# populate devices combos
		"""
		devices = printers
		devices['Serial Port'] = 'add'
		self.set_model_from_list(combo,devices)
		#combo = builder.get_object("device2")
		#self.set_model_from_list(combo,devices)
		"""
		# serial port options
		if os.name == 'posix':
			from bin.serial.scanlinux import scan
			ports = scan()
		# fk windows
		#elif os.name == 'nt':
		#	from scanwin32 import *
		else:
			from scan import scan
			ports = scan()
			
		
		combo = builder.get_object("port")
		self.set_model_from_list(combo,ports)
		combo.set_active(len(ports)-1)
		
		combo = builder.get_object("baudrate")
		self.set_model_from_list(combo,[2400,4800,9600,19200,38400,57600,115200])
		combo.set_active(2)
		
		combo = builder.get_object("parity")
		self.set_model_from_list(combo,['None','Odd','Even','Mark','Space'])
		combo.set_active(0)
		
		combo = builder.get_object("stopbits")
		self.set_model_from_list(combo,[1,1.5,2])
		combo.set_active(0)
		
		combo = builder.get_object("bytesize")
		self.set_model_from_list(combo,[8,7,6,5])
		combo.set_active(0)
		
		# optimize order
		combo = builder.get_object("order_combo")
		self.set_model_from_list(combo,['Complete one copy at a time (default)','Best tracking (min vinyl movement)','Fastest path (min pen movement)'])
		combo.set_active(0)

		# Color cutting
		combo = builder.get_object("color_cut_combo")
		self.set_model_from_list(combo,['All colors #######','Black #000000','White #ffffff','Red #ff0000','Blue #0000ff','Green #00ff00'])
		combo.set_active(0)
		#Plot language HPGL, DMPL or GPGL
		combo = builder.get_object("cmb_plotlang")
		self.set_model_from_list(combo,['Normal plotlanguage (HPGL)','Other plotlanguage (DMPL)','Summa D620 (DMPL)','Jimeile (DMPL)','Other DMPL-plotters','GPGL-plotters (Graphtec)'])
		combo.set_active(0)
		
		# predefined materials parsed from config/materials.xml
		combo = builder.get_object("material")
		materials=['User defined']
		xml = etree.parse(os.path.join(appPath,'config','materials.xml')).getroot()
		for material in xml:
			materials.append(material.attrib['name'])
		self.set_model_from_list(combo,materials)
		combo.set_active(0)
#LW2013 Contourcutting	
	def calculate_degree(self):
		length= self.gui['Yax'].get_value() * units['cm'] #cm to pixels 
		x0 = self.gui['edt_1x'].get_text()  #plotterunits!
		x1 = self.gui['edt_2x'].get_text()  #plotterunits!
		x= int(x1) - int(x0) # Difference in X-axis
		x= (x * units['in']) / 1016 #plotterunits to cm, then to pixels
		sinus = x / length  #calculate sinus
		rotate = (sinus * (180 / math.pi)) *  math.pi # Normal degrees
#		message = gtk.MessageDialog(type=gtk.MESSAGE_ERROR, buttons=gtk.BUTTONS_OK)
#		message.set_markup('X: ' + str(x) + ' Length:' + str(length)+ ' sinus: ' + str(sinus) + ' rotate:' + str(rotate) )
#		message.run()
#		message.destroy()
		return(rotate)	
#First Mark
	def on_btn_first_mark_clicked(self, entry):
		x= self.gui['edt_1x'].get_text()
		y= self.gui['edt_1y'].get_text()
		self.move_cuthead("IN;PU;PR"+ x +","+ y +";")
#1Y
	def on_btn_1y1_clicked(self, entry):
		factor = self.get_factor(1)
		self.move_cuthead("IN;PU;PR0,"+ str(1*factor) +";")
		y = int(self.gui['edt_1y'].get_text() ) + 1 * factor
		self.gui['edt_1y'].set_text( str(y) )
		home_y = int(self.gui['edt_home_y'].get_text() ) + 1 * factor
		self.gui['edt_home_y'].set_text( str(home_y) )
	def on_btn_1_y1_clicked(self, entry):
		factor = self.get_factor(1)
		self.move_cuthead("IN;PU;PR0,"+ str(-1*factor) +";")
		y = int(self.gui['edt_1y'].get_text() ) - 1 * factor
		self.gui['edt_1y'].set_text( str(y) )
		home_y = int(self.gui['edt_home_y'].get_text() ) - 1 * factor
		self.gui['edt_home_y'].set_text( str(home_y) )
	def on_btn_1y10_clicked(self, entry):
		factor = self.get_factor(1)
		self.move_cuthead("IN;PU;PR0,"+ str(10 * factor) + ";")
		y = int(self.gui['edt_1y'].get_text() ) + 10 * factor
		self.gui['edt_1y'].set_text( str(y) )
		home_y = int(self.gui['edt_home_y'].get_text() ) + 10 * factor
		self.gui['edt_home_y'].set_text( str(home_y) )
	def on_btn_1_y10_clicked(self, entry):
		factor = self.get_factor(1)
		self.move_cuthead("IN;PU;PR0,"+ str(-10 * factor) + ";")
		y = int(self.gui['edt_1y'].get_text() ) - 10 * factor
		self.gui['edt_1y'].set_text( str(y) )
		home_y = int(self.gui['edt_home_y'].get_text() ) - 10 * factor
		self.gui['edt_home_y'].set_text( str(home_y) )
#1X
	def on_btn_1x1_clicked(self, entry):
		factor = self.get_factor(1)
		self.move_cuthead("IN;PU;PR"+ str(1 * factor) + ",0;")
		x = int(self.gui['edt_1x'].get_text() ) + 1 * factor
		self.gui['edt_1x'].set_text( str(x) )
		home_x = int(self.gui['edt_home_x'].get_text() ) + 1 * factor
		self.gui['edt_home_x'].set_text( str(home_x) )
#		message = gtk.MessageDialog(type=gtk.MESSAGE_ERROR, buttons=gtk.BUTTONS_OK)
#		message.set_markup("IN;PU;PR"+ str(1 * factor) + ",0;" )
#		message.run()
#		message.destroy()
	def on_btn_1_x1_clicked(self, entry):
		factor = self.get_factor(1)
		self.move_cuthead("IN;PU;PR"+ str(-1 * factor) + ",0;")
		x = int(self.gui['edt_1x'].get_text() ) - 1 * factor
		self.gui['edt_1x'].set_text( str(x) )
		home_x = int(self.gui['edt_home_x'].get_text() ) - 1 * factor
		self.gui['edt_home_x'].set_text( str(home_x) )
	def on_btn_1x10_clicked(self, entry):
		factor = self.get_factor(1)
		self.move_cuthead("IN;PU;PR"+ str(10 * factor) + ",0;")
		x = int(self.gui['edt_1x'].get_text() ) + 10 * factor
		self.gui['edt_1x'].set_text( str(x) )
		home_x = int(self.gui['edt_home_x'].get_text() ) + 10 * factor
		self.gui['edt_home_x'].set_text( str(home_x) )
	def on_btn_1_x10_clicked(self, entry):
		factor = self.get_factor(1)
		self.move_cuthead("IN;PU;PR"+ str(-10 * factor) + ",0;")
		x = int(self.gui['edt_1x'].get_text() ) - 10 * factor
		self.gui['edt_1x'].set_text( str(x) )
		home_x = int(self.gui['edt_home_x'].get_text() ) - 10 * factor
		self.gui['edt_home_x'].set_text( str(home_x) )
#Zero btn mark1
	def on_btn_zero_1_clicked(self, entry):
 		self.gui['edt_1x'].set_text( '0' )
 		self.gui['edt_1y'].set_text( '0' )

#Second Mark
	def on_btn_second_mark_clicked(self, entry):
		x= self.gui['edt_2x'].get_text()
		y= self.gui['edt_2y'].get_text()
#		message = gtk.MessageDialog(type=gtk.MESSAGE_ERROR, buttons=gtk.BUTTONS_OK)
#		message.set_markup('Go to: X: ' + x + ' Y:' + y )
#		message.run()	
		self.move_cuthead("IN;PU;PR"+ x +","+ y +";")
#2Y
	def on_btn_2y1_clicked(self, entry):
		factor = self.get_factor(2)
		self.move_cuthead("IN;PU;PR0,"+ str(1*factor) +";")
		y = int(self.gui['edt_2y'].get_text() ) + 1 * factor
		self.gui['edt_2y'].set_text( str(y) )
		home_y = int(self.gui['edt_home_y'].get_text() ) + 1 * factor
		self.gui['edt_home_y'].set_text( str(home_y) )
	def on_btn_2_y1_clicked(self, entry):
		factor = self.get_factor(2)
		self.move_cuthead("IN;PU;PR0,"+ str(-1*factor) +";")
		y = int(self.gui['edt_2y'].get_text() ) - 1 * factor
		self.gui['edt_2y'].set_text( str(y) )
		home_y = int(self.gui['edt_home_y'].get_text() ) - 1 * factor
		self.gui['edt_home_y'].set_text( str(home_y) )
	def on_btn_2y10_clicked(self, entry):
		factor = self.get_factor(2)
		self.move_cuthead("IN;PU;PR0,"+ str(10 * factor) + ";")
		y = int(self.gui['edt_2y'].get_text() ) + 10 * factor
		self.gui['edt_2y'].set_text( str(y) )
		home_y = int(self.gui['edt_home_y'].get_text() ) + 10 * factor
		self.gui['edt_home_y'].set_text( str(home_y) )
	def on_btn_2_y10_clicked(self, entry):
		factor = self.get_factor(2)
		self.move_cuthead("IN;PU;PR0,"+ str(-10 * factor) + ";")
		y = int(self.gui['edt_2y'].get_text() ) - 10 * factor
		self.gui['edt_2y'].set_text( str(y) )
		home_y = int(self.gui['edt_home_y'].get_text() ) - 10 * factor
		self.gui['edt_home_y'].set_text( str(home_y) )
#2X
	def on_btn_2x1_clicked(self, entry):
		factor = self.get_factor(2)
		self.move_cuthead("IN;PU;PR"+ str(1 * factor) + ",0;")
		x = int(self.gui['edt_2x'].get_text() ) + 1 * factor
		self.gui['edt_2x'].set_text( str(x) )
		home_x = int(self.gui['edt_home_x'].get_text() ) + 1 * factor
		self.gui['edt_home_x'].set_text( str(home_x) )
#		message = gtk.MessageDialog(type=gtk.MESSAGE_ERROR, buttons=gtk.BUTTONS_OK)
#		message.set_markup("IN;PU;PR"+ str(1 * factor) + ",0;" )
#		message.run()
#		message.destroy()
	def on_btn_2_x1_clicked(self, entry):
		factor = self.get_factor(2)
		self.move_cuthead("IN;PU;PR"+ str(-1 * factor) + ",0;")
		x = int(self.gui['edt_2x'].get_text() ) - 1 * factor
		self.gui['edt_2x'].set_text( str(x) )
		home_x = int(self.gui['edt_home_x'].get_text() ) - 1 * factor
		self.gui['edt_home_x'].set_text( str(home_x) )
	def on_btn_2x10_clicked(self, entry):
		factor = self.get_factor(2)
		self.move_cuthead("IN;PU;PR"+ str(10 * factor) + ",0;")
		x = int(self.gui['edt_2x'].get_text() ) + 10 * factor
		self.gui['edt_2x'].set_text( str(x) )
		home_x = int(self.gui['edt_home_x'].get_text() ) + 10 * factor
		self.gui['edt_home_x'].set_text( str(home_x) )
	def on_btn_2_x10_clicked(self, entry):
		factor = self.get_factor(2)
		self.move_cuthead("IN;PU;PR"+ str(-10 * factor) + ",0;")
		x = int(self.gui['edt_2x'].get_text() ) - 10 * factor
		self.gui['edt_2x'].set_text( str(x) )
		home_x = int(self.gui['edt_home_x'].get_text() ) - 10 * factor
		self.gui['edt_home_x'].set_text( str(home_x) )
#Zero btn mark2
	def on_btn_zero_2_clicked(self, entry):
 		self.gui['edt_2x'].set_text( '0' )
 		self.gui['edt_2y'].set_text( '0' )

#btn home 
	def on_btn_home_clicked(self, entry):
		x = 0 - ( int( self.gui['edt_home_x'].get_text() )+0 ) #15 units lower as startingpoint is good
		y = 0 - ( int( self.gui['edt_home_y'].get_text() )+0 )
		self.move_cuthead("IN;PU;PR"+ str(x) +","+ str(y) +";")
#		message = gtk.MessageDialog(type=gtk.MESSAGE_ERROR, buttons=gtk.BUTTONS_OK)
#		message.set_markup('X: ' + str(x) + ' Y: ' + str(y) )
#		message.run()
# factor
	def get_factor(self, mark):
		if self.gui['chk_'+str(mark)+'x10'].get_active():
			factor= 100
		else:
			factor = 1
		return factor
#LW2013 Moving the head without write to a file	
	def move_cuthead(self, hpgl):
		dev = Device(self.read_dev_settings())
		if self.gui['cmb_plotlang'].get_active() == 0 :
			hpgl = hpgl;
		else:
			hpgl = self.plot.toDMPL( hpgl, self.gui['cmb_plotlang'].get_active() )
#		message = gtk.MessageDialog(type=gtk.MESSAGE_ERROR, buttons=gtk.BUTTONS_OK)
#		message.set_markup('Data to plotter:' + hpgl  )
#		message.run()
#		message.destroy()
		dev.plot(None, hpgl)	

	def get_combobox_active_text(self,combobox):
	   model = combobox.get_model()
	   active = combobox.get_active()
	   if active < 0:
		  return None
	   return model[active][0]
	
	def set_model_from_list (self,cb, items):
		"""Setup a ComboBox or ComboBoxEntry based on a list of strings."""		   
		model = gtk.ListStore(str)
		for i in items:
			model.append([i])
		cb.set_model(model)
		if type(cb) == gtk.ComboBoxEntry:
			cb.set_text_column(0)
		elif type(cb) == gtk.ComboBox:
			cell = gtk.CellRendererText()
			cb.pack_start(cell, True)
			cb.add_attribute(cell, 'text', 0)

	
	def on_preview_clicked(self,data=None):
		psvg = preview.hpgl(self.plot)
		filename = os.path.join(appPath,'tmp','InkCutPreview.svg')
		f = open(filename,'w+')
		svgstring = etree.tostring(psvg)
		f.write(svgstring)
		f.close()
		if self.gui['inkscape_preview'].get_active() and not data == 'first':
			try:
				self.inkscapePreviewProcess.kill()
			except:
				self.inkscapePreviewProcess = None
				
			self.inkscapePreviewProcess = subprocess.Popen(['inkscape',filename],stdout=open(LOG_FILENAME,'a'),stderr=open(LOG_FILENAME,'a'))			
		else:
			#self.set_settings('last')
			#-----------------------show preview --------------------
			w  = float(psvg.get('width'))
			h = float(psvg.get('height'))
			scale = 320.0/h
			loader = gtk.gdk.PixbufLoader( 'svg' )
			loader.set_size(int(w*scale),320)
			loader.write(svgstring)
			loader.close()
			pb = loader.get_pixbuf()
			self.gui['preview1'].set_from_pixbuf( pb )
		
	
	def on_cut_clicked(self,button):
		# cut it out
#		if self.gui['dmpl_checkbox'].get_active():
#			hpgl = self.plot.toDMPL()
#		else:
#			hpgl = self.plot.toHPGL()
		#check on combo plot-languages
		if self.gui['cmb_plotlang'].get_active() == 0 :
			hpgl = self.plot.toHPGL()
		if self.gui['cmb_plotlang'].get_active() == 5 :
			hpgl = self.plot.toGPGL( None, self.gui['cmb_plotlang'].get_active() )
		else:
			hpgl = self.plot.toDMPL( None, self.gui['cmb_plotlang'].get_active() )

		if self.gui['file-box'].get_active():
			f = open(self.gui['filechooserbutton1'].get_filename()+os.sep+'inkcut.hpgl','w+')
			f.write(hpgl)
			f.close()
		
		if self.gui['cutter-box'].get_active():
			f = open(os.path.join(appPath,'tmp','plot.hpgl'),'w+')
			f.write(hpgl)
			f.close()
		
		buffer =  self.gui['plotdata'].get_buffer()
		buffer.set_text(hpgl)
		
		buffer =  self.gui['plotdetails'].get_buffer()
		text = "Plot data size (characters): %i \n"%(len(hpgl))
		text +="Vinyl used: %.2fcm \n"%(round(self.plot.size[0]/units['cm'],2))
#LW2013: which port or printer has the output?
		device = str( self.get_combobox_active_text(self.gui['interface']).lower() )
		if device == 'serial':
			device += ': ' + str(self.get_combobox_active_text(self.gui['port'])) + ' : ' + str(self.get_combobox_active_text(self.gui['baudrate']))
		else:
			device += ': ' + str(self.get_combobox_active_text(self.gui['printer']))		
		text += "Send to: "+ device 
		#text +="Estimated time: %d minutes \n"%((self.plot.length)/(self.plot.velocity*60*units['cm']))
		buffer.set_text(text)
		
		
		self.plot_dialog.run()
		self.plot_dialog.hide()

	def on_color_cut_changed(self,combo):
		color = self.gui['color_cut_combo'].get_active()
		self.plot.setColor(color)		

	def on_send_clicked(self,button):
		dev = Device(self.read_dev_settings())
		dev.plot(os.path.join(appPath,'tmp','plot.hpgl'), None)
		
	def on_interface_changed(self,button):
		x = 0

	def on_pause_clicked(self,button):
		x = 0
	
	def on_material_changed(self,combobox,data=None):
		selected = self.get_combobox_active_text(self.gui['material'])
		if (selected != 'User defined'):
			size = material.getSize(selected)
			self.gui['material-width'].set_value(size[0]);
			self.gui['material-length'].set_value(size[1]) # len...
			# material_size_changed is called...
	
	def on_material_size_changed(self,spinbutton=None,data=None):
		y = self.gui['material-width'].get_value();
		x = self.gui['material-length'].get_value();
		self.plot.setDimensions((x*units['cm'],y*units['cm']))
	
	def on_pos_value_changed(self,spinbutton=None,data=None):
		x = self.gui['posnx'].get_value()
		y = self.gui['posny'].get_value()
		pos = (x*units['cm'],y*units['cm'])
		self.plot.setStartPosition(pos)
	
	def on_spacing_value_changed(self,spinbutton=None,data=None):
		r = self.gui['spacing-row'].get_value();
		c = self.gui['spacing-col'].get_value();
		self.plot.setSpacing((c*units['cm'],r*units['cm']))
	
	def on_device_size_value_changed(self,spinbutton=None,data=None):
		y = self.gui['device-width'].get_value();
		x = self.gui['device-length'].get_value();
		self.plot.setMaxDimensions(x*units['cm'],y*units['cm'])
	
	def on_margin_value_changed(self,spinbutton=None,data=None):
		self.plot.setMargin(self.gui['margin'].get_value()*units['cm'])
		
	def on_velocity_value_changed(self,spinbutton=None,data=None):
		self.plot.velocity = self.gui['velocity'].get_value()
	
	def on_force_value_changed(self,spinbutton=None,data=None):
		self.plot.force = self.gui['force'].get_value()
	
	def on_scale_value_changed(self,spinbutton=None,data=None):
		self.plot.setScale(self.gui['scale'].get_value()*1016/units['in'])

	def on_copies_value_changed(self,spinbutton=None,data=None):
		self.plot.setCopies(self.gui['copies'].get_value())
			
	def on_feeding_group_changed(self,spinbutton=None,data=None):
		if self.gui['feeding1'].get_active():
			self.plot.setFinishPosition((0,0))
		if self.gui['feeding2'].get_active():
			self.plot.feed = self.gui['feed'].get_value()*units['cm']
			pos = (self.plot.feed+self.plot.size[0],0)
			self.plot.setFinishPosition(pos)
	
	# weeding
	def on_weed_v_box_toggled(self,box):
		if box.get_active():
			self.plot.weedVertical = True
		else:
			self.plot.weedVertical = False
	
	def on_weed_h_box_toggled(self,box):
		if box.get_active():
			self.plot.weedHorizontal = True
		else:
			self.plot.weedHorizontal = False
	
	def on_weed_box_toggled(self,box):
		if box.get_active():
			self.plot.weedBox = True
		else:
			self.plot.weedBox = False
	
	# order		
	def on_order_changed(self,combo):
		if self.gui['order_box'].get_active():
			# look in populate combo for order
			selected = combo.get_active()
			if selected == 1: # best tracking...
				self.plot.sortTracking = True
				self.plot.sortFastest = False
			elif selected == 2:
				self.plot.sortTracking = False
				self.plot.sortFastest = True
			else:
				self.plot.sortTracking = False
				self.plot.sortFastest = False
		else:
			self.plot.sortTracking = False
			self.plot.sortFastest = False

	#path settings		
	def on_smoothness_value_changed(self,spinbutton=None,data=None):
		self.plot.setSmoothness(self.gui['smoothness'].get_value()*units['mm'])
		
	def on_offset_value_changed(self,spinbutton=None,data=None):
		if self.gui['offset-box'].get_active():
			self.plot.setBladeOffset(self.gui['offset'].get_value()*units['mm'])
		else:
			self.plot.setBladeOffset(0)
	
	def on_overcut_value_changed(self,spinbutton=None,data=None):
		if self.gui['overcut-box'].get_active():
			self.plot.setOvercut(self.gui['overcut'].get_value()*units['mm'])
		else:
			self.plot.setOvercut(0)
	
	def on_invertbox_toggled(self,spinbutton=None,data=None):
		if self.gui['invert-box'].get_active():
			if not self.plot.graphic.mirror[1]:
				self.plot.graphic.mirrorYAxis()
		else:
			if self.plot.graphic.mirror[1]:
				self.plot.graphic.mirrorYAxis()
	def on_stack_btn_clicked(self,copies):
		cur = int(copies.get_value())
		c = self.plot.getStackSize()+cur
		if cur == 1 and c>2: 
			c -= 1
		copies.set_value(c)
		
	def on_reset_stack_btn_clicked(self,copies):
		copies.set_value(1)
	
	def on_defaults_clicked(self):
		self.settings.load('default')
		
	def on_calibration_value_changed(self,adj):
		self.plot.setCalibration(adj.get_value())
	
	def on_cutSettings_toggled(self,box):
		logging.debug(box.get_active())
		if box.get_active():
			self.plot.cutSettings = True
		else:
			self.plot.cutSettings = False
		
	def on_test_connection_clicked(self,widget):
#		message = gtk.MessageDialog(type=gtk.MESSAGE_ERROR, buttons=gtk.BUTTONS_OK)
#		message.set_markup('Widget: ' + self.gui['device1'] )
#		message.run()
#		message.destroy()
		self.set_device_combo(self.gui['device1'])
		dev = Device(self.read_dev_settings())
		hpgl = "IN;PU0,0;PD0,2000;PD2000,2000;PD2000,0;PD0,0;PU0,0;IN;"
		self.move_cuthead( hpgl)
#		dev.plot(os.path.join(appPath,'tests','test.hpgl'), None)
		
	def read_dev_settings(self):
		s = {'width':self.gui['device-width'],
			'length':self.gui['device-length'],
			'name':self.get_combobox_active_text(self.gui['printer']),
			'interface': self.get_combobox_active_text(self.gui['interface']).lower(),
			'serial': {'port':self.get_combobox_active_text(self.gui['port']),
					'baud':int(self.get_combobox_active_text(self.gui['baudrate']))
				}
			}
		return s
	
	# ------------ window management ------------------
	def gtk_main_quit( self, window ):
		self.settings.save('last')
		try:
			self.inkscapePreviewProcess.kill()
		except:
			x = 0 #dummy
			
		gtk.main_quit()
		
	def gtk_window_hide(self,window):
		self.window.hide();

	def on_about_clicked( self, button ):
		# Run dialog
		self.about_dialog.run()
		self.about_dialog.hide()
	
	def on_properties_clicked( self, button ):
		# Run dialog
		self.properties_dialog.run()
		self.properties_dialog.hide()

	def on_concut_clicked( self, button ):
		# Run dialog
		self.concut_dialog.run()
		self.concut_dialog.hide()
	
	def on_openlog_clicked( self, button ):
		
		log = open(LOG_FILENAME,'r')
		buffer =  self.gui['textviewlog'].get_buffer()
		buffer.set_text(log.read())
		log.close()
		self.log_dialog.run()
		self.log_dialog.hide()

def InkscapePlugin(svg,nodes,inkex):
	app = Application(svg,nodes,inkex)
	app.window.show_all()
	gtk.main()
	
if __name__ == "__main__":	
	app = Application(etree.parse(sys.stdin), sys.argv[1:])
	app.window.show_all()
	sys.stdin.close()
	gtk.main()
