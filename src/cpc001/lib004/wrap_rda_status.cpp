#include <boost/python.hpp>
using boost::python::class_;
using boost::python::scope;

#include "wrap_rda_status.h"

extern "C"
{
    #include "rda_status.h"
}

namespace rpg
{
    void export_rda_status()
    {
        scope in_rdastatus = class_<rdastatus_ns>("rdastatus");
            in_rdastatus.attr("RS_RDA_STATUS") = RS_RDA_STATUS;
            in_rdastatus.attr("RS_OPERABILITY_STATUS") = RS_OPERABILITY_STATUS;
            in_rdastatus.attr("RS_CONTROL_STATUS") = RS_CONTROL_STATUS;
            in_rdastatus.attr("RS_AUX_POWER_GEN_STATE") = RS_AUX_POWER_GEN_STATE;
            in_rdastatus.attr("RS_AVE_TRANS_POWER") = RS_AVE_TRANS_POWER;
            in_rdastatus.attr("RS_REFL_CALIB_CORRECTION") = RS_REFL_CALIB_CORRECTION;
            in_rdastatus.attr("RS_DATA_TRANS_ENABLED") = RS_DATA_TRANS_ENABLED;
            in_rdastatus.attr("RS_VCP_NUMBER") = RS_VCP_NUMBER;
            in_rdastatus.attr("RS_RDA_CONTROL_AUTH") = RS_RDA_CONTROL_AUTH;
            in_rdastatus.attr("RS_RDA_BUILD_NUM") = RS_RDA_BUILD_NUM;
            in_rdastatus.attr("RS_OPERATIONAL_MODE") = RS_OPERATIONAL_MODE;
            in_rdastatus.attr("RS_SUPER_RES") = RS_SUPER_RES;
            in_rdastatus.attr("RS_CMD") = RS_CMD;
            in_rdastatus.attr("RS_AVSET") = RS_AVSET;
            in_rdastatus.attr("RS_RDA_ALARM_SUMMARY") = RS_RDA_ALARM_SUMMARY;
            in_rdastatus.attr("RS_COMMAND_ACK") = RS_COMMAND_ACK;
            in_rdastatus.attr("RS_CHAN_CONTROL_STATUS") = RS_CHAN_CONTROL_STATUS;
            in_rdastatus.attr("RS_SPOT_BLANKING_STATUS") = RS_SPOT_BLANKING_STATUS;
            in_rdastatus.attr("RS_BPM_GEN_DATE") = RS_BPM_GEN_DATE;
            in_rdastatus.attr("RS_BPM_GEN_TIME") = RS_BPM_GEN_TIME;
            in_rdastatus.attr("RS_NWM_GEN_DATE") = RS_NWM_GEN_DATE;
            in_rdastatus.attr("RS_NWM_GEN_TIME") = RS_NWM_GEN_TIME;
            in_rdastatus.attr("RS_VC_REFL_CALIB_CORRECTION") = RS_VC_REFL_CALIB_CORRECTION;
            in_rdastatus.attr("RS_TPS_STATUS") = RS_TPS_STATUS;
            in_rdastatus.attr("RS_RMS_CONTROL_STATUS") = RS_RMS_CONTROL_STATUS;
            in_rdastatus.attr("RS_PERF_CHECK_STATUS") = RS_PERF_CHECK_STATUS;
            in_rdastatus.attr("RS_ALARM_CODE1") = RS_ALARM_CODE1;
            in_rdastatus.attr("RS_ALARM_CODE2") = RS_ALARM_CODE2;
            in_rdastatus.attr("RS_ALARM_CODE3") = RS_ALARM_CODE3;
            in_rdastatus.attr("RS_ALARM_CODE4") = RS_ALARM_CODE4;
            in_rdastatus.attr("RS_ALARM_CODE5") = RS_ALARM_CODE5;
            in_rdastatus.attr("RS_ALARM_CODE6") = RS_ALARM_CODE6;
            in_rdastatus.attr("RS_ALARM_CODE7") = RS_ALARM_CODE7;
            in_rdastatus.attr("RS_ALARM_CODE8") = RS_ALARM_CODE8;
            in_rdastatus.attr("RS_ALARM_CODE9") = RS_ALARM_CODE9;
            in_rdastatus.attr("RS_ALARM_CODE10") = RS_ALARM_CODE10;
            in_rdastatus.attr("RS_ALARM_CODE11") = RS_ALARM_CODE11;
            in_rdastatus.attr("RS_ALARM_CODE12") = RS_ALARM_CODE12;
            in_rdastatus.attr("RS_ALARM_CODE13") = RS_ALARM_CODE13;
            in_rdastatus.attr("RS_ALARM_CODE14") = RS_ALARM_CODE14
        ;

        //
        // wideband status line values
        //

        in_rdastatus.attr("RS_NOT_IMPLEMENTED") = RS_NOT_IMPLEMENTED;
        in_rdastatus.attr("RS_CONNECT_PENDING") = RS_CONNECT_PENDING;
        in_rdastatus.attr("RS_DISCONNECT_PENDING") = RS_DISCONNECT_PENDING;
        in_rdastatus.attr("RS_DISCONNECTED_HCI") = RS_DISCONNECTED_HCI;
        in_rdastatus.attr("RS_DISCONNECTED_CM") = RS_DISCONNECTED_CM;
        in_rdastatus.attr("RS_DISCONNECTED_SHUTDOWN") = RS_DISCONNECTED_SHUTDOWN;
        in_rdastatus.attr("RS_CONNECTED") = RS_CONNECTED;
        in_rdastatus.attr("RS_DOWN") = RS_DOWN;
        in_rdastatus.attr("RS_WBFAILURE") = RS_WBFAILURE;
        in_rdastatus.attr("RS_DISCONNECTED_RMS") = RS_DISCONNECTED_RMS;

        //
        // command ack status values
        //

        in_rdastatus.attr("RS_NO_ACKNOWLEDGEMENT") = RS_NO_ACKNOWLEDGEMENT;
        in_rdastatus.attr("RS_REMOVE_VCP_RECEIVED") = RS_REMOTE_VCP_RECEIVED;
        in_rdastatus.attr("RS_CLUTTER_BYPASS_MAP_RECEIVED") = RS_CLUTTER_BYPASS_MAP_RECEIVED;
        in_rdastatus.attr("RS_CLUTTER_CENSOR_ZONES_RECEIVED") = RS_CLUTTER_CENSOR_ZONES_RECEIVED;
        in_rdastatus.attr("RS_REDUND_CHNL_STBY_CMD_ACCEPTED") = RS_REDUND_CHNL_STBY_CMD_ACCEPTED;

        //
        // RDA status states
        //

        in_rdastatus.attr("RS_STARTUP") = RS_STARTUP;
        in_rdastatus.attr("RS_STANDBY") = RS_STANDBY;
        in_rdastatus.attr("RS_RESTART") = RS_RESTART;
        in_rdastatus.attr("RS_OPERATE") = RS_OPERATE;
        in_rdastatus.attr("RS_OFFOPER") = RS_OFFOPER;

        //
        // RDA operability status
        //

        in_rdastatus.attr("OS_INDETERMINATE") = OS_INDETERMINATE;
        in_rdastatus.attr("OS_ONLINE") = OS_ONLINE;
        in_rdastatus.attr("OS_MAINTENANCE_REQ") = OS_MAINTENANCE_REQ;
        in_rdastatus.attr("OS_MAINTENANCE_MAN") = OS_MAINTENANCE_MAN;
        in_rdastatus.attr("OS_COMMANDED_SHUTDOWN") = OS_COMMANDED_SHUTDOWN;
        in_rdastatus.attr("OS_INOPERABLE") = OS_INOPERABLE;
        in_rdastatus.attr("OS_WIDEBAND_DISCONNECT") = OS_WIDEBAND_DISCONNECT;
    }
}

