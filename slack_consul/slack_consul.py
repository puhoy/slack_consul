import os
import consul
import requests
from time import sleep
import logging
import json
from collections import OrderedDict
from slack_consul.config import conf
from logstash_formatter import LogstashFormatterV1

conf['slack_link'] = os.environ.get('SC_SLACK_LINK', False)  # link to report to
conf['notify_users'] = os.environ.get('SC_NOTIFY_USERS', '').split(
    ',')  # users to add to message with @user
conf['consul_address'] = os.environ.get('SC_CONSUL_ADDRESS', 'consul.service.consul')  # consul address
conf['consul_port'] = int(os.environ.get('SC_CONSUL_PORT', 8500))  # consul address
if os.environ.get('SC_ADDITIONAL_VARS', False):
    conf['additional_vars'] = os.environ.get('SC_ADDITIONAL_VARS').split(
        ',')  # additional vars to append to message (fetched from consul)
else:
    conf['additional_vars'] = []

conf['bot_name'] = os.environ.get('SC_BOT_NAME', 'infradiff bot')
conf['slack_channel'] = os.environ.get('SC_SLACK_CHANNEL', None)

conf['loglevel'] = os.environ.get('SC_LOGLEVEL', 'production')
conf['connected'] = True


loglevel = {
    "production": logging.INFO,
    "debug": logging.DEBUG
}


logger = logging.getLogger()
logger.setLevel(loglevel[conf['loglevel']])
handler = logging.StreamHandler()
formatter = LogstashFormatterV1()

handler.setFormatter(formatter)
logger.addHandler(handler)


RED = "#cc0000"
YELLOW = "#e6e600"
GREEN = "#36a64f"


def send_to_slack(j):
    if conf['slack_channel']:
        j['channel'] = conf['slack_channel']
    j["username"] = conf['bot_name']
    j["icon_emoji"] = ":ghost:"
    ret = requests.post(conf['slack_link'], json=j)
    logger.info(ret.text)


def get_consul():
    try:
        c = consul.Consul(host=conf['consul_address'], port=conf['consul_port'])
        c.status.leader()
        conf['connected'] = True
    except Exception as e:
        msg = "cant connect to consul!"
        for user in conf['notify_users']:
            msg += ' @%s' % user
        if conf['connected']:
            send_to_slack({"text": msg,
                           "attachments": [{
                               "text": '%s' % e,
                               "color": RED
                           }]})
        logger.error('cant connect to consul! (%s)' % e)
        conf['connected'] = False
        return False
    return c


def get_additional_vars():
    c = get_consul()
    if not c:
        return {}
    vars = {}
    for var in conf['additional_vars']:
        index, data = c.kv.get(var)
        if data:
            vars[var] = data.get('Value', None).decode("utf-8")
        else:
            vars[var] = "null"
    return vars


def get_diff_nodes(old_service, new_service):
    missing_nodes_in_service = set(old_service) - set(new_service)
    new_nodes_in_service = set(new_service) - set(old_service)
    return list(new_nodes_in_service), list(missing_nodes_in_service)


def get_diff_services(old, new):
    missing_nodes = {}
    new_nodes = {}

    new_services = list(set(new) - set(old))
    missing_services = list(set(old) - set(new))

    all_services = set(old).union(set(new))
    for service in all_services:
        old_service = old.get(service, {})
        new_service = new.get(service, {})
        added, missing = get_diff_nodes(old_service, new_service)
        if added:
            new_nodes[service] = added
        if missing:
            missing_nodes[service] = missing

    return {'new_services': new_services,
            'missing_services': missing_services,
            'new_nodes': new_nodes,
            'missing_nodes': missing_nodes}


def get_health(state):
    c = get_consul()
    if not c:
        return {}
    services = c.health.state(state)[1]
    new_health = {}

    for service in services:
        if service['ServiceID']:
            new_health[service['ServiceID']] = service
    return new_health


def get_services():
    c = get_consul()
    if not c:
        return {}
    nodes = c.catalog.services()
    new_services = {}
    # logger.debug(nodes)
    for node, vals in nodes.items():
        service = vals['Service']
        if not new_services.get(service, False):
            new_services[service] = []
        new_services[service].append(node)
    return new_services


def slack_start(services):
    msg = 'starting! i have the following services: \n'
    nodes_text = ''
    for service, nodes in services.items():
        if len(nodes) == 1:
            term = 'node'
        else:
            term = 'nodes'
        nodes_text += '- %s (%s %s)\n' % (service, len(nodes), term)

    vars = get_additional_vars()
    vars_to_send = []
    for k, v in vars.items():
        vars_to_send.append({"title": k,
                             "value": v,
                             "short": False})
    j = {
        "text": msg,
        "attachments": [
            {
                "text": nodes_text,
                "color": GREEN
            },
        ]
    }
    if vars_to_send:
        j["attachments"].append({
            "text": "you told me to append these variables",
            "fields": vars_to_send
        })

    logger.info('sending on slack: %s' % json.dumps(j, indent=2))
    send_to_slack(j)


def get_diff_health(old_health, new_health):
    diff = {}
    for state in ['critical', 'passing', 'warning']:
        diff[state] = {}
        new = set(new_health[state]) - set(old_health[state])
        for item in new:
            diff[state][item] = new_health[state][item]
    return diff


def slack_health(health):
    print(health)
    colors = {
        'critical': RED,
        'warning': YELLOW,
        'passing': GREEN
    }

    for state, service_dict in health.items():
        j = {"text": 'new services in %s state' % state,
             "attachments": [],
             }

        for k, details in service_dict.items():
            s = {
                "text": details['ServiceID'],
                "fields": [
                    {
                        "title": "Output",
                        "value": details['Output'],
                    }
                ]
            }
            if colors.get(state, False):
                s["color"] = colors[state]
            j["attachments"].append(s)

        if j["attachments"]:
            send_to_slack(j)


def slack_diff(difference):
    logger.info('slacking diff...')
    msg = "something happened! "
    if conf['notify_users']:
        for user in conf['notify_users']:
            msg += ' @%s' % user
    new_services = difference['new_services']
    missing_services = difference['missing_services']
    new_nodes = difference['new_nodes']
    missing_nodes = difference['missing_nodes']

    j = {"username": conf['bot_name'],
         "text": msg,
         "attachments": []
         }
    vars = get_additional_vars()
    vars_to_send = []
    for k, v in vars.items():
        vars_to_send.append({"title": k,
                             "value": v,
                             "short": False})
    if vars_to_send:
        j["attachments"].append({
            "text": "you told me to append these variables from consul",
            "fields": vars_to_send
        })

    if new_services:
        t = "new services! (yay!)\n"
        t += ", ".join(new_services)
        j["attachments"].append({
            "text": t,
            "color": GREEN
        })
    if missing_services:
        t = "missing services!\n"
        t += ", ".join(missing_services)
        j["attachments"].append({
            "text": t,
            "color": RED
        })

    if missing_nodes:
        nodes_kv = []
        for service, nodes in missing_nodes.items():
            nodes_kv.append({"title": service,
                             "value": ', '.join(nodes),
                             "short": False})

        j["attachments"].append({
            "text": "missing nodes!",
            "fields": nodes_kv,
            "color": RED,
        })

    if new_nodes:
        nodes_kv = []
        for service, nodes in new_nodes.items():
            logger.info(nodes)
            nodes_kv.append({"title": service,
                             "value": ', \n'.join(nodes),
                             "short": False})

        j["attachments"].append({
            "text": "new nodes!",
            "color": GREEN,
            "fields": nodes_kv
        })
    send_to_slack(j)


def has_empty_values(d):
    for k, v in d.items():
        if d[k]:
            return False
    return True


def loop(timeout=10):
    no_diff = {'new_services': [],
               'missing_services': [],
               'new_nodes': {},
               'missing_nodes': {}}
    new_services = OrderedDict(sorted(get_services().items()))
    while not new_services:
        new_services = OrderedDict(sorted(get_services().items()))
        sleep(timeout)
    services = new_services
    slack_start(new_services)

    health = {
        'passing': get_health('passing'),
        'warning': get_health('warning'),
        'critical': get_health('critical')
    }

    while True:
        try:
            new_services = OrderedDict(sorted(get_services().items()))
        except Exception as e:
            logger.error('error getting services: %s' % e)
            send_to_slack({"text": 'error getting services',
                           "attachments": [{
                               "text": '%s' % e,
                               "color": RED
                           }]})
            continue
        diff = get_diff_services(old=services, new=new_services)
        if diff == {}:
            # there was en error while connection to consul that should be already handled
            continue

        logger.debug(diff)
        logger.debug(no_diff)
        if not has_empty_values(diff):
            # logger.info('diff in services! new services: %s' % new_services)
            slack_diff(diff)
            services = new_services

        # health
        new_health = {
            'passing': get_health('passing'),
            'warning': get_health('warning'),
            'critical': get_health('critical')
        }

        health_diff = get_diff_health(health, new_health)
        if not has_empty_values(health_diff):
            slack_health(health_diff)
            health = new_health
        sleep(timeout)


if __name__ == '__main__':
    logger.info('starting!')
    logger.info('using %s' % conf['slack_link'])
    loop()
