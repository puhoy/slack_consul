## get slack notification about differences in consul services


### envvars

    SC_SLACK_LINK - slack api link to post the messages to 
    SC_NOTIFY_USERS - comma separated list of users
    SC_CONSUL_ADDRESS - consul address, default: consul.service.consul
    SC_CONSUL_PORT' - consul port, default: 8500
    SC_ADDITIONAL_VARS - list of additional vars to report
    SC_BOT_NAME - bot name to use, default: 'infradiff bot'
    SC_SLACK_CHANNEL - channel to post to (overrides config of api link)
    SC_LOGLEVEL - production (info) or debug, default: production

### starting
(create a virtualenv, set your envvars, pip install -e .)

python slack_consul/slack_consul.py
