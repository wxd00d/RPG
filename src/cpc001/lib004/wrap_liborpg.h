#ifndef _RPG_WRAP_LIBORPG_H_
#define _RPG_WRAP_LIBORPG_H_

#include <boost/python.hpp>
using boost::python::tuple;

#include <string>
using std::string;

#include <vector>
using std::vector;

namespace rpg
{
    struct liborpg_ns {};      // dummy struct for namespacing

    int thinwrap_orpg_send_cmd(
        int cmd, 
        int who_sent_it, 
        int param1, 
        int param2, 
        int param3, 
        int param4, 
        int param5, 
        vector<char>& msg
    );
    tuple thinwrap_orpg_statefl_get_rpgalrm();
    tuple thinwrap_orpg_statefl_get_rpgopst();
    string thinwrap_orpgda_lbname(int data_id);

    void wrap_orpgda();
    void wrap_orpgrda();
    void wrap_orpgmisc();
    void wrap_orpginfo();
    void export_liborpg();
}

#endif /* _RPG_WRAP_LIBORPG_H_ */

