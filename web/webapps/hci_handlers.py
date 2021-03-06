from platform import architecture
word_size = int(architecture()[0].replace('bit',''))
if word_size == 32:
    import simplejson as json
else:
    import json
from templating import LOOKUP
import sys
import os
import web
from subprocess import Popen, call, PIPE

def shell_source(script,var):
    """
    Sometime you want to emulate the action of "source" in bash,
    settings some environment variables. Here is a way to do it.
    """
    pipe = Popen(". %s; env" % script, stdout=PIPE, shell=True)
    output = pipe.communicate()[0]
    env = dict((line.split("=", 1) for line in output.splitlines() if var in line or "False" == var))
    os.environ.update(env)


OPERATIONAL = os.path.isfile("/etc/profile.d/rpg.sh")
HOME = os.environ.get("HOME")
if OPERATIONAL:
    shell_source("/etc/profile.d/rpg.sh","False")
    HOME = os.environ.get("RPGHOME")
    shell_source(os.path.join(HOME,".bash_profile"),"RMTPORT")
    RPGLIB = os.environ.get("RPGLIB")
else:
    RPGLIB = os.environ.get("LD_LIBRARY_PATH")

CFG = os.environ.get("CFG_DIR")
sys.path.append(RPGLIB)
sys.path.append(CFG + "/web/deps")


import _rpg
import time
from commands import getoutput
from cgi import parse_qs
import datetime
import StringIO
from gzip import GzipFile
from multiprocessing import Queue, Process, Event
import threading
import base64
import math

VCP_DIR = CFG+'/vcp/'
DE = {'DISABLED':'off','ENABLED':'on'}
SECONDS_PER_HOUR = 3600

months = ['Jan','Feb','Mar','Apr','May','June','July','Aug','Sept','Oct','Nov','Dec']
cfg = str(CFG)
moments = {
	    _rpg.orpgevt.RADIAL_ACCT_REFLECTIVITY:'R',
	    _rpg.orpgevt.RADIAL_ACCT_VELOCITY:'V',
	    _rpg.orpgevt.RADIAL_ACCT_WIDTH:'W',
	    _rpg.orpgevt.RADIAL_ACCT_DUALPOL:'D'
	  }
RPG_op_priority = {
		    'ONLINE':1,
		    'CMDSHDN':2,	
		    'MAR':3,
		    'MAM':4,
		    'LOADSHED':5
		  }
##
# Global Flags initialized as True for initialization of hci. Updated by the callback functions, set to false after being updated, set to True on callback 
##

EN_flags = {
                	    "ORPGEVT_ENVWND_UPDATE":True,
                	    "ORPGEVT_PERF_MAIN_RECEIVED":True,
                	    "ORPGEVT_RPG_STATUS_CHANGE":True,
                	    "ORPGEVT_RPG_OPSTAT_CHANGE":True,
			    "ORPGEVT_RPG_ALARM":True,
                	    "ORPGEVT_RDA_STATUS_CHANGE":True,
                	    "ORPGEVT_RDA_ALARMS_UPDATE":True,
                            "ORPGEVT_ADAPT_UPDATE":True,
                            "ORPGDAT_PRF_COMMAND_INFO": True,
                            "ORPGDAT_RPG_INFO": True,
                            "ORPGDAT_LOAD_SHED_CAT": True,
                            "DEAU":True,
                            "EWT_DATA_ID": True,
			    "ORPGDAT_SYSLOG": True,
                            "ORPGDAT_SYSLOG_LATEST": True,
			    "SAILS_STATUS_ID":True,
                            "MRLE_STATUS_ID":True,
			    "RDA_STATUS_ID":True,
			    "VOL_STAT_GSM_ID":True,
			    "WX_STATUS_ID":True,
			    "HCI_PRECIP_STATUS_MSG_ID":True,
			    "HCI_PROD_INFO_STATUS_MSG_ID":True,
			    "SYSLOG_ALARM":True,	
			    "SYSLOG_STATUS":True
	   }
log_flags = ['SYSLOG_ALARM','SYSLOG_STATUS','ORPGEVT_RPG_ALARM']

update_dict = {}
default_sse_timeout = {'retry':'4000'} # default connection loss timeout for server-sent events
msg = {'retry':'4000'} 
start_msg = {'retry':'4000'}
radome_event_id = 0
update_event = threading.Event()
log_event = threading.Event()
radome_event = threading.Event()


def stripList(list1):
    """ strips lists of square brackets, backslashes, and newlines """
    return str(list1).replace('[','').replace(']','').replace('\'','').strip().strip('\\n')

def hasNumbers(inputString):
    """ checks for digits in string """
    return any(char.isdigit() for char in inputString)

def to_radians(deg):
    return round(( math.radians(deg) ) - math.pi / 2, 2)

def sse_pack_single(d):
    """ Pack data in a single-line Server-Sent Event (SSE) format """
    buffer = ''
    for k in ['retry','id','data','event']:
        if k in d.keys():
            buffer += '%s: %s\n' % (k, d[k])
    return buffer + '\n'

def sse_pack(data,attr):
    """ Packs data in a multi-line Server-Sent Event (SSE) format """
    buffer = 'retry: %s\n\n' % attr['retry']
    for d in xrange(4):
        if d in data.keys():
            buffer += 'id: %s\n' % str(attr['id'+str(d)])
            buffer += 'event: %s\n' % data[d]
            buffer += 'data: %s\n\n' % data['data'+str(d)]
    return buffer

def gzip_response(resp):
    """ Packs server response in the gzip compressed format """
    web.webapi.header('Content-Encoding','gzip')
    zbuf = StringIO.StringIO()
    zfile = GzipFile(mode='wb',fileobj=zbuf,compresslevel=9)
    zfile.write(resp)
    zfile.close()
    data = zbuf.getvalue()
    web.webapi.header('Content-Length',str(len(data)))
    web.webapi.header('Vary','Accept-Encoding',unique=True)
    return data

def RDA_static():
    """ Method for initializing a static RDA Lookup dictionary """ 
    RS_states = {}
    cat_list = [x for x in dir(_rpg.rdastatus) if '_' not in x]
    cat_dict = dict((catname,[x for x in dir(getattr(_rpg.rdastatus,catname)) if '__' not in x]) for catname in cat_list if catname != 'acknowledge' or 'rdastatus_lookup')
    for cat in cat_list:
        temp = dict((getattr(getattr(_rpg.rdastatus,cat),x),x) for x in cat_dict[cat])
        if cat == 'rdastatus':
            temp.update({0:'UNKNOWN'})
        if cat == 'controlstatus' or cat == 'controlauth':
            temp.update({0:'N/A'})
        temp.update({-9999:'-9999'})
        RS_states.update({cat:temp})
    return RS_states

def RPG_static():
    """ Method for initializing a static RPG lookup dictionary """
    RPG_states = {"SAILS":dict((v,k.replace('GS_SAILS_','')) for k,v in _rpg.orpgsails.__dict__.iteritems() if '__' not in k and type(v) == int)}
    RPG_states.update({"MRLE":dict((v,k.replace('GS_MRLE_','')) for k,v in _rpg.orpgsails.orpgmrle.__dict__.iteritems() if '__' not in k and type(v) == int)})
    return RPG_states

"""
Setup DEAU Database LB
"""
n = _rpg.liborpg.orpgda_lbname(_rpg.orpgdat.ORPGDAT_ADAPT_DATA)
_rpg.librpg.deau_lb_name(n)

_rpg.librpg.deau_set_values('alg.Nonoperational.test_mrle',1)

"""
 Separate process for event handling. This is done in order to 
 bypass the Global Interpreter Lock.
 Loads data into a queue which is retrieved by SSE  
"""

dummy_event  = Event()
radome_queue = Queue()
update_queue = Queue()

def radome_funcs(radome_queue):
    """ Container for callbacks """
    def RADOME_callback(event, msg_data):
        """ Register pbd radial update callbacks for HCI radome items """
        msg = _rpg.orpgevt.to_orpgevt_radial_acct_t(msg_data)
        data = {
                'moments':msg.moments,
                'sails_seq':msg.sails_cut_seq,
                'mrle_seq':msg.mrle_cut_seq,
                'radial_status':msg.radial_status, 
                'az':to_radians(msg.azimuth/10),
                'el':msg.elevation/float(10),
                'start_az':to_radians(msg.start_elev_azm/10),
	        'last_elev':msg.last_ele_flag
                }
        radome_queue.put(data) 
    
    _rpg.liben.en_register(_rpg.orpgevt.ORPGEVT_RADIAL_ACCT, RADOME_callback)
    dummy_event.wait()

radome_process = Process(target=radome_funcs, args=(radome_queue,))
radome_process.start()

def update_funcs(update_queue):
    """ container for callbacks """
    AN_dict = dict((v,k) for k,v in _rpg.orpgevt.__dict__.iteritems() if 'ORPGEVT' in k)
    UN_dict = dict((_rpg.liborpg.orpgda_lbfd(v),k) for k,v in _rpg.orpgdat.__dict__.iteritems() if 'ORPGDAT' in k)
    UN_dict.update({_rpg.liborpg.orpgda_lbfd(((_rpg.lb.EWT_UPT/_rpg.lb.ITC_IDRANGE)*_rpg.lb.ITC_IDRANGE)):"EWT_DATA_ID"})
    EN_dict = AN_dict.copy()
    EN_dict.update(UN_dict)
    UN_msgids = {"ORPGDAT_GSM_DATA":dict((k,str(v)) for k,v in _rpg.orpgdat.Orpgdat_gsm_data_msg_id_t.values.iteritems())}
    UN_msgids.update({"ORPGDAT_HCI_DATA":dict((k,str(v)) for k,v in _rpg.orpgdat.Orpgdat_hci_data_msg_id_t.values.iteritems())})
    UN_msgids.update({"ORPGDAT_SYSLOG_LATEST":{1:"SYSLOG_STATUS",2:"SYSLOG_ALARM"}})

    """ generic callback all events are registered to """
    def generic_callback(fd,msg):
	valid = EN_dict.get(fd)
	if valid:
	    if valid in UN_msgids.keys():
	        flag = UN_msgids[EN_dict[fd]][msg]
	    else:
		flag = EN_dict[fd]
	else:
	    flag = "DEAU" 
	update_queue.put(flag)

    """ Register DEAU Update Notification Callback """

    _rpg.liben.deau_un_register('',generic_callback)	
    
    """ Register Application Notification (AN) Callbacks """
   
    AN_reg = dict((k,v) for k,v in _rpg.orpgevt.__dict__.iteritems() if 'ORPGEVT' in k and 'RADIAL_ACCT' not in k and 'LOAD_SHED' not in k)
    for k,v in AN_reg.iteritems():
        _rpg.liben.en_register(v,generic_callback)

    """ Register LB Update Notification (UN) Callbacks """

    ewt_data_id = ((_rpg.lb.EWT_UPT/_rpg.lb.ITC_IDRANGE)*_rpg.lb.ITC_IDRANGE)
    _rpg.liben.un_register(ewt_data_id,_rpg.lb.LBID_EWT_UPT,generic_callback)
    _rpg.liben.un_register(_rpg.orpgdat.ORPGDAT_RPG_INFO,_rpg.orpgdat.Orpginfo_msgids_t.ORPGINFO_STATEFL_SHARED_MSGID,generic_callback)
    _rpg.liben.un_register(_rpg.orpgdat.ORPGDAT_PRF_COMMAND_INFO,_rpg.orpgdat.ORPGDAT_PRF_STATUS_MSGID,generic_callback)
    _rpg.liben.un_register_multi(_rpg.orpgdat.ORPGDAT_SYSLOG_LATEST,1,generic_callback)
    _rpg.liben.un_register_multi(_rpg.orpgdat.ORPGDAT_SYSLOG_LATEST,2,generic_callback)
    _rpg.liben.un_register_multi(_rpg.orpgdat.ORPGDAT_GSM_DATA,_rpg.orpgdat.Orpgdat_gsm_data_msg_id_t.SAILS_STATUS_ID,generic_callback)
    _rpg.liben.un_register_multi(_rpg.orpgdat.ORPGDAT_GSM_DATA,_rpg.orpgdat.Orpgdat_gsm_data_msg_id_t.MRLE_STATUS_ID,generic_callback)
    _rpg.liben.un_register_multi(_rpg.orpgdat.ORPGDAT_GSM_DATA,_rpg.orpgdat.Orpgdat_gsm_data_msg_id_t.RDA_STATUS_ID,generic_callback)
    _rpg.liben.un_register_multi(_rpg.orpgdat.ORPGDAT_GSM_DATA,_rpg.orpgdat.Orpgdat_gsm_data_msg_id_t.VOL_STAT_GSM_ID,generic_callback)
    _rpg.liben.un_register_multi(_rpg.orpgdat.ORPGDAT_GSM_DATA,_rpg.orpgdat.Orpgdat_gsm_data_msg_id_t.WX_STATUS_ID,generic_callback)
    _rpg.liben.un_register_multi(_rpg.orpgdat.ORPGDAT_HCI_DATA,_rpg.orpgdat.Orpgdat_hci_data_msg_id_t.HCI_PROD_INFO_STATUS_MSG_ID,generic_callback)
    _rpg.liben.un_register_multi(_rpg.orpgdat.ORPGDAT_HCI_DATA,_rpg.orpgdat.Orpgdat_hci_data_msg_id_t.HCI_PRECIP_STATUS_MSG_ID,generic_callback)
   
     
    dummy_event.wait()  # hold the process so it doesn't return 

update_process = Process(target=update_funcs, args=(update_queue,))
update_process.start()


""" Initialize items used by init functions """

prf_dict = dict((_rpg.Prf_status_t.__dict__[x],x.replace('PRF_COMMAND_','')) for x in _rpg.Prf_status_t.__dict__ if 'PRF_COMMAND' in x)
nb_dict = dict((v,k) for k,v in _rpg.libhci.nb_status.__dict__.items() if '__' not in k)

RS_states = RDA_static()
RPG_states = RPG_static()
RS_dict_init = {}


""" 
Fxn defs to initialize data on initial server connect and on callbacks 
"""

def VAD_init():	
    if (EN_flags['ORPGEVT_ENVWND_UPDATE']):
        vad_flag = _rpg.libhci.hci_get_vad_update_flag()
	EN_flags['ORPGEVT_ENVWND_UPDATE'] = False
        return {'VAD_Update':vad_flag}
    else:
	return False

def PMD_init():
    if (EN_flags['ORPGEVT_PERF_MAIN_RECEIVED']):	
        pmd = _rpg.libhci.hci_get_orda_pmd_ptr().pmd	
    	EN_flags['ORPGEVT_PERF_MAIN_RECEIVED'] = False
	return {
   	    'cnvrtd_gnrtr_fuel_lvl':pmd.cnvrtd_gnrtr_fuel_lvl,
	    'perf_check_time':pmd.perf_check_time
        }
    else:
	return False

def RPG_state_init():
    if (EN_flags['ORPGEVT_RPG_STATUS_CHANGE']):
        RPG_state_list = [x for x in dir(_rpg.orpgmisc) if 'ORPGMISC' in x]
        RPG_state = [task.replace('ORPGMISC_IS_RPG_STATUS_','') for task in RPG_state_list if _rpg.liborpg.orpgmisc_is_rpg_status(getattr(_rpg.orpgmisc,task))]
        if not RPG_state:
            RPG_state.append("SHUTDOWN")
	
	EN_flags['ORPGEVT_RPG_STATUS_CHANGE'] = False	
	return {'RPG_state':",".join(RPG_state)}

    else:
	return False

def RS_init():
    if (EN_flags['ORPGEVT_RDA_STATUS_CHANGE']):
        RS_dict = {}
        RS_list = [x for x in dir(_rpg.rdastatus) if 'RS' in x]
        for task in RS_list:
            RS_dict.update({task:_rpg.liborpg.orpgrda_get_status(getattr(_rpg.rdastatus,task))})
	RS_dict.update({'RS_DATA_TRANS_ENABLED':str(RS_dict['RS_DATA_TRANS_ENABLED'] >> 2 & 7)})
        oper_list = [RS_states['opstatus'][key].replace('OS_','') for key in RS_states['opstatus'].keys() if (key & RS_dict['RS_OPERABILITY_STATUS']) > 0]
        if not oper_list:
            oper_list.append('UNKNOWN')
        aux_gen_list = [RS_states['auxgen'][key].strip('AP_').strip('RS_') for key in RS_states['auxgen'].keys() if (key & RS_dict['RS_AUX_POWER_GEN_STATE']) > 0]
	RS_dict.update({'RS_AUX_POWER_GEN_STATE':["GENERATOR_ON" in aux_gen_list,"UTILITY_PWR_AVAIL" in aux_gen_list]})
        alarm_list = [RS_states['alarmsummary'][key].strip('AS_-9999') for key in RS_states['alarmsummary'].keys() if (key & RS_dict['RS_RDA_ALARM_SUMMARY']) > 0 or key == RS_dict['RS_RDA_ALARM_SUMMARY']]
	wbstat = _rpg.liborpg.orpgrda_get_wb_status(_rpg.orpgrda.ORPGRDA_WBLNSTAT)
	blanking = _rpg.liborpg.orpgrda_get_wb_status(_rpg.orpgrda.ORPGRDA_DISPLAY_BLANKING)
	blanking_state = (blanking and (RS_dict['RS_CONTROL_STATUS'] == _rpg.rdastatus.controlstatus.CS_LOCAL_ONLY)) or not (wbstat == _rpg.rdastatus.wideband.RS_CONNECTED or wbstat == _rpg.rdastatus.wideband.RS_DISCONNECT_PENDING)
	power_state_blanking = blanking != _rpg.rdastatus.RS_AUX_POWER_GEN_STATE
	control_state_blanking = blanking != _rpg.rdastatus.RS_CONTROL_STATUS
	control_auth = blanking == 0 or blanking == _rpg.rdastatus.RS_RDA_CONTROL_AUTH and wbstat == _rpg.rdastatus.wideband.RS_CONNECTED or wbstat == _rpg.rdastatus.wideband.RS_DISCONNECT_PENDING
	RS_dict.update({
			'RS_RDA_CONTROL_AUTH':RS_states['controlauth'][RS_dict['RS_RDA_CONTROL_AUTH']],
        		'CONTROL_AUTHORITY': control_auth,
			'BLANKING_VALID':[blanking_state,power_state_blanking,control_state_blanking],
                        'RS_REFL_CALIB_CORRECTION':(abs(RS_dict['RS_REFL_CALIB_CORRECTION']) >= 200, "%0.2f" % (float(RS_dict['RS_REFL_CALIB_CORRECTION']) / 100)),
                        'RS_VC_REFL_CALIB_CORRECTION':(abs(RS_dict['RS_VC_REFL_CALIB_CORRECTION']) >= 200, "%0.2f" % (float(RS_dict['RS_VC_REFL_CALIB_CORRECTION']) / 100))
		      })
	RS_dict_init.update(RS_dict)
	EN_flags['ORPGEVT_RDA_STATUS_CHANGE'] = False
        return {
	'RDA_static':
	    {
               'CS':RS_states['controlstatus'][RS_dict['RS_CONTROL_STATUS']],
               'TPS_STATUS':RS_states['tps'][RS_dict['RS_TPS_STATUS']].strip('TP_'),
               'OPERABILITY_LIST':oper_list[0],
               'RS_RDA_ALARM_SUMMARY_LIST':filter(None,alarm_list),
               'RDA_STATE':RS_states['rdastatus'][RS_dict['RS_RDA_STATUS']].replace('RS_',''),
               'WIDEBAND':RS_states['wideband'][wbstat].replace('RS_',''),
	       'DISPLAY_BLANKING':RS_states['wideband'][blanking].replace('RS_','')	
	    }
        }
    else:
	return False	


def RDA_alarms_init():
    if (EN_flags['ORPGEVT_RDA_ALARMS_UPDATE']):
        try:
	    alarm_status = _rpg.liborpg.orpgrda_get_alarm(_rpg.liborpg.orpgrda_get_num_alarms()-1,_rpg.orpgrda.ORPGRDA_ALARM_CODE)
            latest_alarm_text = _rpg.liborpg.orpgrat_get_alarm_text(_rpg.liborpg.orpgrda_get_alarm(_rpg.liborpg.orpgrda_get_num_alarms()-1,_rpg.orpgrda.ORPGRDA_ALARM_ALARM))
            yr = str(_rpg.liborpg.orpgrda_get_alarm(_rpg.liborpg.orpgrda_get_num_alarms()-1,_rpg.orpgrda.ORPGRDA_ALARM_YEAR))
            mo = _rpg.liborpg.orpgrda_get_alarm(_rpg.liborpg.orpgrda_get_num_alarms()-1,_rpg.orpgrda.ORPGRDA_ALARM_MONTH)
            day = _rpg.liborpg.orpgrda_get_alarm(_rpg.liborpg.orpgrda_get_num_alarms()-1,_rpg.orpgrda.ORPGRDA_ALARM_DAY)
            hr = _rpg.liborpg.orpgrda_get_alarm(_rpg.liborpg.orpgrda_get_num_alarms()-1,_rpg.orpgrda.ORPGRDA_ALARM_HOUR)
            min = _rpg.liborpg.orpgrda_get_alarm(_rpg.liborpg.orpgrda_get_num_alarms()-1,_rpg.orpgrda.ORPGRDA_ALARM_MINUTE)
            sec = _rpg.liborpg.orpgrda_get_alarm(_rpg.liborpg.orpgrda_get_num_alarms()-1,_rpg.orpgrda.ORPGRDA_ALARM_SECOND)
            latest_alarm_timestamp = months[mo-1]+' '+str(day)+','+yr[2]+yr[3]+' ['+'%02d' % hr+':'+'%02d' % min+':'+'%02d' % sec+']'
            alarm = _rpg.liborpg.orpgda_read_syslog(_rpg.orpgdat.ORPGDAT_SYSLOG_LATEST,_rpg.libhci.HCI_LE_MSG_MAX_LENGTH,2)
	    if alarm[0] > 0:
                tstamp_alarm = alarm[2];
                ts = datetime.datetime(int(yr),mo,day,hr,min,sec)
                uts = time.mktime(ts.timetuple())
                precedence = ts>tstamp_alarm
	    else:
 	        precedence = True
            latest_alarm = {'valid':1,'precedence':precedence,'alarm_status':alarm_status,'timestamp':latest_alarm_timestamp,'text':latest_alarm_text}
        except:
            latest_alarm = {'valid':0}

	EN_flags['ORPGEVT_RDA_ALARMS_UPDATE'] = False
        return {'latest_alarm':latest_alarm}
    else:
	False

def RPG_alarm_init():
    if(EN_flags['ORPGEVT_RPG_ALARM']):
        RPG_alarms_iter = _rpg.orpginfo.orpgalarms.values.iteritems()
        RPG_alarms = [str(v).replace('ORPGINFO_STATEFL_RPGALRM_','') for k,v in RPG_alarms_iter if k & _rpg.liborpg.orpginfo_statefl_get_rpgalrm()[1] > 0]
        EN_flags['ORPGEVT_RPG_ALARM'] = False
        return {'RPG_alarms':RPG_alarms}
    else:
	return False
 


def syslog_alarm_init():
    if(EN_flags['SYSLOG_ALARM']): 
        alarm = _rpg.liborpg.orpgda_read_syslog(_rpg.orpgdat.ORPGDAT_SYSLOG_LATEST,_rpg.libhci.HCI_LE_MSG_MAX_LENGTH,2)
	if alarm[0] > 0:
	    parse_alarm = alarm[1].split(':')
            tstamp_alarm = alarm[2]
            alarm_date = datetime.datetime.utcfromtimestamp(tstamp_alarm).strftime('%b %-d,%y [%H:%M:%S]')
            mask = [alarm[3] & v for k,v in _rpg.lb.le.__dict__.iteritems() if 'MASK' in k and alarm[3] & v > 0]
	    if mask:
                msg_type = [k for k,v in _rpg.lb.le.__dict__.iteritems() if 'MASK' not in k and v == mask[0]][0]	
	    else:
		msg_type = False
            active = [k for k,v in _rpg.lb.le.__dict__.iteritems() if 'CLEAR' in k and alarm[3] & v > 0] == []
            error = alarm[3] & _rpg.lb.le.HCI_LE_ERROR_BIT > 0
            alarm_text = alarm_date +' >> '+":".join(parse_alarm[1:]).replace('\n','')
        else:
	    alarm_text = 'ORPGDA_read error'
	    msg_type = ''
	    active = ''
	    error = ''  
	EN_flags['SYSLOG_ALARM'] = False
        return {
            'alarm_text':alarm_text,
	    'alarm_msg_type':msg_type.replace('HCI_LE_',''),
	    'alarm_active':active,
	    'alarm_error':error
        }
    else:
	return False

def RPG_op_init():
    if (EN_flags['ORPGEVT_RPG_OPSTAT_CHANGE']):
	RPG_op_iter = _rpg.orpginfo.opstatus.values.iteritems()
        RPG_op = [str(v).replace('ORPGINFO_STATEFL_RPGOPST_','') for k,v in RPG_op_iter if k & _rpg.liborpg.orpginfo_statefl_get_rpgopst()[1] > 0]
        RPG_op_tupled = [(RPG_op_priority[x],x) for x in RPG_op]
	RPG_op_tupled_sort = sorted(RPG_op_tupled, key=lambda op: op[0])
	RPG_op = [x[1] for x in RPG_op_tupled_sort]
	return {'RPG_op':RPG_op}
        EN_flags['ORPGEVT_RPG_OPSTAT_CHANGE'] = False
    else:
	return False

def ADAPT_init():
    if (EN_flags['DEAU']):
        ICAO = _rpg.librpg.deau_get_string_values('site_info.rpg_name')
        zr_relation = _rpg.librpg.deau_get_string_values('alg.hydromet_rate.ZR_relationship')
        ptype = _rpg.librpg.deau_get_string_values('alg.dp_precip.Precip_type') 
        max_sails = _rpg.librpg.deau_get_string_values('pbd.n_sails_cuts')
        max_mrle = _rpg.librpg.deau_get_string_values('pbd.n_mrle_cuts')
	default_wx_mode = _rpg.librpg.deau_get_string_values(_rpg.librpg.ORPGSITE_DEA_WX_MODE)
        default_mode_A_vcp = _rpg.librpg.deau_get_values(_rpg.librpg.ORPGSITE_DEA_DEF_MODE_A_VCP,1)
        default_mode_B_vcp = _rpg.librpg.deau_get_values(_rpg.librpg.ORPGSITE_DEA_DEF_MODE_B_VCP,1)
        precip_switch = _rpg.libhci.hci_get_mode_a_auto_switch_flag()
        clear_air_switch = _rpg.libhci.hci_get_mode_b_auto_switch_flag()	
	EN_flags['DEAU'] = False
        return {
	    'ICAO':ICAO[1],
	    'ZR':zr_relation[1],
	    'ptype':ptype[1],
	    'max_sails':max_sails[1],
            'max_mrle':max_mrle[1],
	    'default_wx_mode':default_wx_mode[1].replace(' ','-'),
	    'default_mode_A':default_mode_A_vcp[1][0],
	    'default_mode_B':default_mode_B_vcp[1][0],
            'mode_A_auto_switch':precip_switch,
            'mode_B_auto_switch':clear_air_switch

        }
    else:
	return False

def LOADSHED_init():
    if (EN_flags['ORPGDAT_LOAD_SHED_CAT']):
        category_dict = dict((str(v),k) for k,v in _rpg.liborpg.LOAD_SHED_CATEGORY.values.items())
        type_dict = dict((str(v),k) for k,v in _rpg.liborpg.LOAD_SHED_TYPE.values.items())
        loadshed_dict = {}
        loadshed = {}
        for c in category_dict:
            temp = {}
            for t in type_dict:
                temp.update({t:_rpg.liborpg.orpgload_get_data(category_dict[c],type_dict[t])[1]})
            loadshed_dict.update({c:temp})
        for cat in loadshed_dict:
            if(loadshed_dict[cat]['LOAD_SHED_CURRENT_VALUE'] >=loadshed_dict[cat]['LOAD_SHED_WARNING_THRESHOLD']):
                loadshed[cat] = 'WARNING'
            elif(loadshed_dict[cat]['LOAD_SHED_CURRENT_VALUE'] >=loadshed_dict[cat]['LOAD_SHED_ALARM_THRESHOLD']):
                loadshed[cat] = 'ALARM'
            else:
                loadshed[cat] = 'NONE'

        EN_flags['ORPGDAT_LOAD_SHED_CAT'] = False
        return {'loadshed':loadshed}
    else:
        return False



def CRDA_init():
    if (EN_flags['RDA_STATUS_ID']):
        CRDA_dict = {}
        try:
            lookup = dict((v,k) for k,v in _rpg.rdastatus.rdastatus_lookup.__dict__.items() if '__' not in k)
            CMD = _rpg.liborpg.orpgrda_get_status(_rpg.rdastatus.RS_CMD)
            AVSET = _rpg.liborpg.orpgrda_get_status(_rpg.rdastatus.RS_AVSET)
            CRDA_dict.update({'RS_CMD_STATUS':lookup.get(CMD,"ENABLED").replace('CMD_','') if CMD >= 0 else "????"})
            CRDA_dict.update({'RS_AVSET_STATUS':lookup.get(AVSET,"ENABLED").replace('AVSET_','') if AVSET > 0 else "????"})
        except:
            pass
        EN_flags['RDA_STATUS_ID'] = False
        return CRDA_dict
    else:
        return False

def syslog_status_init():
    if (EN_flags['SYSLOG_STATUS']):
        status = _rpg.liborpg.orpgda_read_syslog(_rpg.orpgdat.ORPGDAT_SYSLOG_LATEST,_rpg.libhci.HCI_LE_MSG_MAX_LENGTH,1)
        if status[0] > 0:
            parse_status = status[1].split(':')
            text_status = ":".join(parse_status[1:]).replace('\n','')
            tstamp_s = status[2]
            date_s = datetime.datetime.utcfromtimestamp(tstamp_s).strftime('%b %-d,%y [%H:%M:%S]')
            rpg_status = date_s + " >> " + text_status
            mask = [status[3] & v for k,v in _rpg.lb.le.__dict__.iteritems() if 'MASK' in k and status[3] & v]
            if mask:
                msg_type = [k.replace('HCI_LE_','') for k,v in _rpg.lb.le.__dict__.iteritems() if v == mask[0] and 'MASK' not in k][0]
            else:
                msg_type = False
            cleared = [k for k,v in _rpg.lb.le.__dict__.iteritems() if 'CLEAR' in k and status[3] & v] != []
            error = status[3] & _rpg.lb.le.HCI_LE_ERROR_BIT
        else:
            rpg_status = 'ORPGDA_read error'
            rpg_status_ts = ''
            tstamp_s = ''
            msg_type = ''
            cleared = ''
            error = status[0]
        EN_flags['SYSLOG_STATUS'] = False

        return {
            'status_msgs':rpg_status,
            'status_ts':tstamp_s,
            'msg_type':msg_type,
            'cleared':cleared,
            'error':error
        }
    else:
       return False

def syslog_status_next():
    status = _rpg.liborpg.orpgda_read_syslog(_rpg.orpgdat.ORPGDAT_SYSLOG,_rpg.libhci.HCI_LE_MSG_MAX_LENGTH,_rpg.lb.LB_NEXT)
    if status[0] > 0:
        parse_status = status[1].split(':')
        text_status = ":".join(parse_status[1:]).replace('\n','')
        tstamp_s = status[2]
        date_s = datetime.datetime.utcfromtimestamp(tstamp_s).strftime('%b %-d,%y [%H:%M:%S]')
	rpg_status = date_s + " >> " + text_status
	mask = [status[3] & v for k,v in _rpg.lb.le.__dict__.iteritems() if 'MASK' in k and status[3] & v]
	if mask:
	    msg_type = [k.replace('HCI_LE_','') for k,v in _rpg.lb.le.__dict__.iteritems() if v == mask[0] and 'MASK' not in k][0]
        else:
            if status[3] & _rpg.lb.le.HCI_LE_ERROR_BIT:
                msg_type = "RPG_STATUS_WARN"
	    else:
	        msg_type = False
	cleared = [k for k,v in _rpg.lb.le.__dict__.iteritems() if 'CLEAR' in k and status[3] & v] != []
	error = status[3] & _rpg.lb.le.HCI_LE_ERROR_BIT 
    else:
        rpg_status = 'ORPGDA_read error'
        rpg_status_ts = ''
        tstamp_s = ''
        msg_type = ''
        cleared = ''
        error = status[0]
	
    return {
            'status_msgs':rpg_status,
            'status_ts':tstamp_s,
	    'msg_type':msg_type,
	    'cleared':cleared,
	    'error':error
    }

def RPG_syslog_init():
    log = _rpg.liborpg.orpgda_read_syslog_full(_rpg.orpgdat.ORPGDAT_SYSLOG)
    if log[0] > 0:
        text = [":".join(x.split(':')[1:]).replace('\n','') for x in log[3]]
	status_msgs = [datetime.datetime.utcfromtimestamp(x).strftime('%b %-d,%y [%H:%M:%S]') + " >> " + text[i] for i,x in enumerate(log[1])]
	mask = [[x & v for k,v in _rpg.lb.le.__dict__.iteritems() if 'MASK' in k and x & v] for x in log[2]]
        cleared = [[x & v for k,v in _rpg.lb.le.__dict__.iteritems() if 'CLEAR' in k and x & v] != [] for x in log[2]]
	msg_type = []	
	for i,m in enumerate(mask):
            if m:
                msg_type.append([k.replace('HCI_LE_','') for k,v in _rpg.lb.le.__dict__.iteritems() if v == m[0] and 'MASK' not in k][0])
            else:	
		if log[2][i] & _rpg.lb.le.HCI_LE_ERROR_BIT:	
		    msg_type.append("RPG_STATUS_WARN")
		else:
                    msg_type.append(False)
    else:
        status_msgs = 'ORPGDAT_SYSLOG read failure:%d' % log[0]
	msg_type = ''
	active = ''	
    return { 'status_msgs':status_msgs,
	     'msg_type':msg_type,
	     'cleared':cleared
	     
    }
		    

def NB_status_init():
    if (EN_flags['HCI_PROD_INFO_STATUS_MSG_ID']): 
        nb = _rpg.libhci.hci_get_nb_connection_status()
        
	EN_flags['HCI_PROD_INFO_STATUS_MSG_ID'] = False
	
	return {'narrowband':nb_dict[nb]}
    else:
	return False

def model_flag_init():
    if (EN_flags['EWT_DATA_ID']):
        model_flag = _rpg.libhci.hci_get_model_update_flag()
        EN_flags['EWT_DATA_ID'] = False
	return {'Model_Update':model_flag}
    else:
	return False

def SAILS_init():
    if (EN_flags['SAILS_STATUS_ID']):
	sails_status = _rpg.liborpg.orpgda_read_sails(_rpg.orpgdat.ORPGDAT_GSM_DATA,_rpg.orpgdat.Orpgdat_gsm_data_msg_id_t.SAILS_STATUS_ID)
	if sails_status[0] > 0:
	    sails_cuts = sails_status[1]
        else:
	    print "ORPGDAT_GSM_DATA read failed:%d" % sails_status[0]
	    sails_cuts = 0
        sails_allowed = _rpg.orpgsails.orpgsails_allowed()
        sails_active = RPG_states['SAILS'][_rpg.orpgsails.orpgsails_get_status()]
	EN_flags['SAILS_STATUS_ID'] = False
        return {
	    'sails_cuts':sails_cuts,
            'sails_status':sails_active,
	    'sails_allowed':sails_allowed
        }
    else:
	return False

def MRLE_init():
    if (EN_flags['MRLE_STATUS_ID']):
        mrle_status = _rpg.liborpg.orpgda_read_mrle(_rpg.orpgdat.ORPGDAT_GSM_DATA,_rpg.orpgdat.Orpgdat_gsm_data_msg_id_t.MRLE_STATUS_ID)
        if mrle_status[0] > 0:
            mrle_cuts = mrle_status[1]
        else:
            print "ORPGDAT_GSM_DATA read failed:%d" % mrle_status[0]
            mrle_cuts = 0
        mrle_allowed = _rpg.orpgsails.orpgmrle.orpgmrle_allowed()
        mrle_active = RPG_states['MRLE'][_rpg.orpgsails.orpgmrle.orpgmrle_get_status()]
        EN_flags['MRLE_STATUS_ID'] = False
        return {
            'mrle_cuts':mrle_cuts,
            'mrle_status':mrle_active,
            'mrle_allowed':mrle_allowed
        }
    else:
        return False
 
def ORPGVST_init():
    if (EN_flags['VOL_STAT_GSM_ID']):
        ORPGVST = time.strftime(' %H:%M:%S UT',time.gmtime(_rpg.liborpg.orpgvst_get_volume_time()/1000))
	EN_flags['VOL_STAT_GSM_ID'] = False
        return {'ORPGVST':ORPGVST}
    else:
	return False

def STATEFL_init():
    if (EN_flags['ORPGDAT_RPG_INFO']):
	EN_flags['ORPGDAT_RPG_INFO'] = False
        return {
    	    'RPG_SAILS':_rpg.orpginfo.orpginfo_is_sails_enabled(),
            'RPG_MRLE':_rpg.orpginfo.orpginfo_is_mrle_enabled(),
            'RPG_AVSET':_rpg.orpginfo.orpginfo_is_avset_enabled(),
            'RPG_CMD':_rpg.orpginfo.orpginfo_is_cmd_enabled()
        }
    else:
	return False

def WX_init():
    if (EN_flags['WX_STATUS_ID']):
        mode_conflict = (_rpg.libhci.hci_get_wx_status().current_wxstatus != _rpg.libhci.hci_get_wx_status().recommended_wxstatus)
        mode_trans = _rpg.libhci.hci_get_wx_status().wxstatus_deselect 
	EN_flags['WX_STATUS_ID'] = False
	return { 
	    'mode_conflict':mode_conflict,
	    'mode_trans':mode_trans
        }
    else:
	return False

def PRECIP_init():
    if (EN_flags['HCI_PRECIP_STATUS_MSG_ID']):
        precip = _rpg.libhci.hci_get_precip_status().current_precip_status    
    
	EN_flags['HCI_PRECIP_STATUS_MSG_ID'] = False
	return {'current_precip_status':precip}
    else:
	return False

def PRF_init():
    if (EN_flags['ORPGDAT_PRF_COMMAND_INFO']):
        prf = _rpg.libhci.hci_get_prf_mode_status_msg().state

	EN_flags['ORPGDAT_PRF_COMMAND_INFO'] = False

        return {'prf':prf_dict[prf]}
    else:
	return False

"""
 Init functions initialize the global dictionary. The callback functions below then set flags which are checked by the init functions and updates when flag is True. 
 The server then checks for changes and pushes updates when necessary
"""

Global_dict = {
	 	'vad_flag':VAD_init(),
                'model_update':model_flag_init(),
                'syslog_status':syslog_status_init(),
		'syslog_alarm':syslog_alarm_init(),
		'PMD':PMD_init(),
		'NB':NB_status_init(),
		'RPG':{
			'RPG_state':RPG_state_init(),
			'RPG_alarm':RPG_alarm_init(),
			'RPG_op':RPG_op_init(),	
		      },
		'RDA':{
			'RDA_static':RS_init(),
			'RDA_alarms':RDA_alarms_init(),
			'CRDA':CRDA_init(),
		      },
		'LOADSHED':LOADSHED_init(),
		'ADAPT':ADAPT_init(),
		'SAILS':SAILS_init(),
                'MRLE':MRLE_init(),
		'ORPGVST':ORPGVST_init(),
		'STATEFL':STATEFL_init(),
		'WX':WX_init(),
		'PRECIP':PRECIP_init(),
		'PRF':PRF_init()
	      }

class MRPG(object):
    """ Controls the RPG throgh mrpg """
    def POST(self):	
	data = parse_qs(web.data())
	status = _rpg.mrpg.orpgmgr_send_command(getattr(_rpg.mrpg.commands,data['COM'][0]))
	if status < 0:	
	    print "ORPGMGR_send_command failed %d" % status
	return status

class Set_Flag(object):
    """ sets flags in libhci """
    def POST(self):
	data = parse_qs(web.data())
	set_type = data['TYPE'][0]
	flag = int(data['FLAG'][0])
	print set_type,flag
	get_type = set_type.replace('set','get')
	get_flag = getattr(_rpg.libhci,get_type)()
	set_flag = getattr(_rpg.libhci,set_type)(flag)
	return json.dumps(set_flag)

class ORPGSAILS_set(object):
    """ sets the number of SAILS cuts """
    def POST(self):
	data = web.input()
        print data
	cuts = int(data.NUM_CUTS)
	commanded_cuts = _rpg.orpgsails.orpgsails_set_req_num_cuts(cuts)
	return json.dumps(commanded_cuts)

class ORPGMRLE_set(object):
    """ sets the number of MRLE cuts """
    def POST(self):
        data = web.input()
        print data
        cuts = int(data.NUM_CUTS)
        commanded_cuts = _rpg.orpgsails.orpgmrle.orpgmrle_set_req_num_cuts(cuts)
        return json.dumps(commanded_cuts)

"""
 Function Lookup Dictionaries 
"""

RS_l = {
	'RDA_static':RS_init,
	'RDA_alarms':RDA_alarms_init,
	'CRDA':CRDA_init
       }

RPG_l = {
             'RPG_alarm':RPG_alarm_init,
             'RPG_state':RPG_state_init,
             'RPG_op':RPG_op_init,
             'SAILS':SAILS_init,
             'MRLE':MRLE_init,
             'ORPGVST':ORPGVST_init,
             'STATEFL':STATEFL_init,
             'syslog_status':syslog_status_init,
             'syslog_alarm':syslog_alarm_init,
             'NB':NB_status_init
        }
		
PMD_l = {
            'LOADSHED':LOADSHED_init,
            'PMD':PMD_init,
            'PRF':PRF_init,
            'PRECIP':PRECIP_init,
            'WX':WX_init,
        }

ADAPT_l = {
            'ADAPT':ADAPT_init,
            'vad_flag':VAD_init,
            'model_update':model_flag_init
          }

def RS(): 
    """ Returns a dictionary of all necessary data from the RDA status message """
    RS_dict = RS_dict_init

    for name, function in RS_l.iteritems():	
	item = function()
	if item:
	    RS_dict.update(item)
	    Global_dict['RDA'][name] = item
	else:
	    RS_dict.update(Global_dict['RDA'][name])
    
    return RS_dict

def RPG():
    """ Returns a dictionary of all necessary RPG states/flags """
    RPG_dict = {}
    for name,function in RPG_l.iteritems():
	item = function()            
	sub = name.split('_')[0]
	if sub == 'RPG':
	    if item:
	        RPG_dict.update(item)
	        Global_dict['RPG'][name] = item 
	    else:
	        RPG_dict.update(Global_dict['RPG'][name])
	else:
	    if item:
		RPG_dict.update(item)
		Global_dict[name] = item 
	    else:
	        RPG_dict.update(Global_dict[name])
    return RPG_dict	


def PMD():   
    """ Returns a dictionary of all Performance/ Maintenance Data and more from libhci. """
 
    PMD_dict = {}
    
    for name,function in PMD_l.iteritems():	
        item = function()
	if item:	
	    PMD_dict.update(item)
	    Global_dict[name] = item
	else:	
	    PMD_dict.update(Global_dict[name])
    
    return PMD_dict	

def ADAPT():
    """ Returns a dictionary of all necessary Adaptation data for the HCI. """
    ADAPT_dict = {}
    
    for name,function in ADAPT_l.iteritems():
	item = function()
	if item:
	    ADAPT_dict.update(item)
	    Global_dict[name] = item
	else:	
	    ADAPT_dict.update(Global_dict[name])
    
    return ADAPT_dict

def CFG():
    """ Method for retrieving all necessary config data by parsing the RPG VCP definitions. """
    allow_sails = {}
    last_elev = {}
    super_res = {}
    mode = {}
    dir_list_parse = [x for x in os.listdir(VCP_DIR) if x.split('_')[0] == 'vcp']
    for vcp in dir_list_parse:
        fname = VCP_DIR+vcp
        try:
            f = open(fname,'r')
            text_lines = list(f)
        except:
            pass
        sails = [int(stripList(x.split('allow_sails')[1])) if 'allow_sails' in x else [0] for x in text_lines if 'allow_sails' in x]
        allow_sails.update({vcp.replace('vcp_',''):sails[0] if sails else 0})
        mode.update({vcp.replace('vcp_',''):[x.replace('wx_mode','').lstrip().replace('\n','') for x in text_lines if 'wx_mode' in x][0]})
    CFG_dict = {
	    'allow_sails':allow_sails,
	    'home':HOME,
	    'cfg':cfg,
	    'mode':mode
	    }
    return CFG_dict 

class IndexView(object):
    """
    Renders the main HCI using the LOOKUP global templating function.
    CFG dict passed for templating 
    """
    def GET(self):
        return LOOKUP.IndexView(**{'CFG_dict':CFG()})

class Update(object):
    """
    Returns data for HCI using a key lookup separated by type or the 
    whole object if key and type are unspecified (standard AJAX method).
    """
    def GET(self):
        function_dict = {'PMD':PMD,'RS':RS,'RPG':RPG,'ADAPT':ADAPT,'CFG':CFG}
        data = web.input()
        t = data.get('t',False) 
	if t and t in function_dict.keys():
            if data.get('key',False):
	        return json.dumps(function_dict[data.t]()[data.key])
            else: 
                return json.dumps(function_dict[data.t]())
        else:
            return gzip_response(json.dumps({'PMD_dict':PMD(),'RS_dict':RS(),'RPG_dict':RPG(),'ADAPT_dict':ADAPT(),'CFG_dict':CFG()}))

class update_generator(threading.Thread):
    """ Generates Update Dicts for Consumption by SSE. """
    def run(self):
        function_dict = {'PMD':PMD,'RS':RS,'RPG':RPG,'ADAPT':ADAPT}	
	while True:
            check_dict = {'PMD':PMD(),'RS':RS(),'RPG':RPG(),'ADAPT':ADAPT()}
	    global EN_flags
            flag = update_queue.get()
            EN_flags[flag] = True
            update_dict.update(dict((k+'_dict',function_dict[k]()) for k,v in check_dict.items() if function_dict[k]() != v)) # compare dicts for changes
            if flag in log_flags:
                log_event.set()
                log_event.clear()
	    if update_dict:	
		update_event.set()
		update_event.clear()

update_gen = update_generator()
update_gen.start()

class Update_Server(object):
    """
    Main Server Sent Updates (SSE) endpoint.  
    """
    def GET(self):
        web.header("Content-Type","text/event-stream")
	web.header("Cache-Control","no-cache")
	attr = default_sse_timeout
	event_id = 0
	while True:
	    if event_id == 0:
		update_dict.update({'PMD_dict':PMD(),'RS_dict':RS(),'RPG_dict':RPG(),'ADAPT_dict':ADAPT()})
	    data = {}	
	    for idx,val in enumerate(update_dict):
  	        data.update({idx:val,'data'+str(idx):json.dumps(update_dict[val])})
	        event_id += 1
	        attr.update({'id'+str(idx):event_id})
	    yield sse_pack(data,attr)
            update_event.wait()

class RPG_status_server(object):
    """
    Endpoint for RPG status log
    """
    def GET(self):
        web.header("Content-Type","text/event-stream")
        web.header("Cache-Control","no-cache") 
	data = default_sse_timeout
	event_id = 0
	wait = False
	while True:
	    if event_id == 0:
	        out = {"syslog":RPG_syslog_init(),"alarms":Global_dict['RPG']['RPG_alarm']['RPG_alarms']}
	    else:
		log = syslog_status_next()
		wait = log['error'] == -38
		out.update({"syslog":log,"alarms":Global_dict['RPG']['RPG_alarm']['RPG_alarms']})
	    data.update({'data':json.dumps(out),'id':event_id})
	    yield sse_pack_single(data)
	    event_id += 1
	    if wait:
                log_event.wait()

class radome_generator(threading.Thread):
    """
    Generates radome updates
    """
    def run(self):
        global radome_event_id
	radome_event_id = 0
	radome_out = {}
        while True:
            radome_update = radome_queue.get()
	    update_all = radome_update.get('radial_status') in [0,3] or radome_event_id == 0
            if update_all:
		radome_update.update({'update':True})
                moments_list = [moments[x] for x in moments.keys() if x & radome_update.get('moments',False) > 0]
                radome_update.update({'moments':moments_list,'moments_mask':radome_update.get('moments',0)})
                start_msg.update({                    
                    'data':json.dumps(radome_update),
                    'id':radome_event_id,
		    'elev_start': True
                })
                radome_event.set()
	    else:
                msg.update({
                    'data':json.dumps({ 
                        'az':radome_update.get('az'),
                        'update':False
                    }),
                    'id':radome_event_id
                })
            radome_event_id += 1 # provide unique event id so the client can distinguish between messages     

radome_gen = radome_generator()
radome_gen.start()
	
class Radome(object):
    """
    Endpoint for radome updates  
    """
    def GET(self):
	web.header("Content-Type","text/event-stream")
	web.header("Cache-Control","no-cache") # caching must be turned off or it will fill up quickly
        initial = True
	while True:
  	    if initial:
                global radome_event_id 
                radome_event_id = 0
                initial = False
                yield sse_pack_single(start_msg)
            radome_event.wait(1)
            if start_msg.get('elev_start') == True:  
                start_msg.update({'elev_start':False})
                radome_event.clear()
                yield sse_pack_single(start_msg)
            else:
                yield sse_pack_single(msg)
 
class ORPGVST(object):
    """
    Retrieves the Volume Scan Start Time
    """
    def GET(self):
        return json.dumps({'ORPGVST':ORPGVST_init()})

##
# Retrieves the current mrpg state
##

class MRPG_state(object):
    def GET(self):
	state = _rpg.mrpg.orpgmgr_get_rpg_states()
	if state[0] < 0:
	    print "ORPGMGR_get_RPG_states failed: %d" % state[0]
	    return json.dumps({'MRPG_state':state[0]})
	else:
	    mrpg = str(_rpg.mrpg.states.values[state[1]])
            return json.dumps({'MRPG_state':mrpg})

##
# Operations Sub-Menu
##
 
class Operations(object):
    def GET(self):
	return LOOKUP.ops(**{'PMD_dict':PMD(),'RS_dict':RS(),'RPG_dict':RPG(),'CFG_dict':CFG()})

##
# RPG Control Sub-Menu
##
 
class Control_RPG(object):
    def GET(self):
        return LOOKUP.control_rpg()

##
# RPG Control Sub-Menu
##

class RPG_Status(object):
    def GET(self):
        return LOOKUP.rpg_status()

##
# Spawns subtasks
##

class Button(object):
    def GET(self):
	selected_button = web.input(id=None)
	if selected_button.id not in getoutput('ps -A'):
	    return Popen(selected_button.id).wait() # //TODO: using wait() can be dangerous, find another way to implement this 
##
# MRPG Clean Startup 
##

class MRPG_clean(object):
    def GET(self):
	ret = call(['mrpg','-p','startup'])
	return ret

##
# DEAU set function
##

class DEAU_set(object):
    def POST(self):
        data = parse_qs(web.data())
	set = data['SET'][0].replace('-',' ')	
	flag = data['FLAG'][0]
	if int(flag):
            mode = data['MODE'][0]
	    ret = _rpg.librpg.deau_set_values(getattr(_rpg.librpg,'ORPGSITE_DEA_DEF_MODE_'+mode+'_VCP'),int(set))
	else:
	    ret = _rpg.librpg.deau_set_string_values(_rpg.librpg.ORPGSITE_DEA_WX_MODE,set)
	return ret

allowed = (
	('ROC','roc1'),
	('URC','urc1'),
	('AGENCY','agency1')
)

##
# Authentication for password protected items
##

class Basic_Auth(object):
    def GET(self):
	auth = web.ctx.env.get("HTTP_AUTHORIZATION").replace('Basic ','')	
	username,password = base64.decodestring(auth).split(':')
	if (username,password) not in allowed:
            web.header('WWW-Authenticate','Basic realm="pass-protect"')
            web.ctx.status = '401 Unauthorized'
	return json.dumps(auth) 
class DQD(object):
    def GET(self):
        #redirect to static file
	raise web.seeother('/static/index.html')
