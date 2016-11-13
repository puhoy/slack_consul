import os
import consul
import requests
from time import sleep
import logging
import json
from collections import OrderedDict
from slack_consul.config import conf

logging.basicConfig(format='%(asctime)s module: %(module)s line: %(lineno)d :: %(message)s',
                    datefmt='%m/%d/%Y %I:%M:%S %p', level=logging.DEBUG)

conf['slack_link'] = os.environ.get('SC_SLACK_LINK', False)  # link to report to
conf['notify_users'] = os.environ.get('SC_NOTIFY_USERS', '').split(
    ',')  # users to add to message with @user
conf['consul_address'] = os.environ.get('SC_CONSUL_ADDRESS', 'consul.service.consul')  # consul address
conf['consul_port'] = int(os.environ.get('SC_CONSUL_PORT', 8500))  # consul address
conf['additional_vars'] = os.environ.get('SC_ADDITIONAL_VARS', '').split(
    ',')  # additional vars to append to message (fetched from consul)

conf['connected'] = True


def send_to_slack(j):
    j["username"] = "infradiff bot"
    j["icon_emoji"] = ":ghost:"
    ret = requests.post(conf['slack_link'], json=j)
    logging.info(ret.text)


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
                               "color": "#cc0000"
                           }]})
        logging.error('cant connect to consul! (%s)' % e)
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


def get_services():
    c = get_consul()
    if not c:
        return {}
    nodes = c.agent.services()
    new_services = {}
    # logging.debug(nodes)
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
                "color": "#36a64f"
            },
        ]
    }
    if vars_to_send:
        j["attachments"].append({
            "text": "you told me to append these variables",
            "fields": vars_to_send
        })

    logging.info('sending on slack: %s' % json.dumps(j, indent=2))
    send_to_slack(j)


def slack_diff(difference):
    logging.info('slacking diff...')
    msg = "something happened! "
    if conf['notify_users']:
        for user in conf['notify_users']:
            msg += ' @%s' % user
    new_services = difference['new_services']
    missing_services = difference['missing_services']
    new_nodes = difference['new_nodes']
    missing_nodes = difference['missing_nodes']

    j = {"username": "infradiff bot",
         "icon_emoji": ":ghost:",
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
            "color": "#36a64f"
        })
    if missing_services:
        t = "missing services!\n"
        t += ", ".join(missing_services)
        j["attachments"].append({
            "text": t,
            "color": "#cc0000"
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
            "color": "#cc0000",
        })

    if new_nodes:
        nodes_kv = []
        for service, nodes in new_nodes.items():
            logging.info(nodes)
            nodes_kv.append({"title": service,
                             "value": ', '.join(nodes),
                             "short": False})

        j["attachments"].append({
            "text": "new nodes!",
            "color": "#36a64f",
            "fields": nodes_kv
        })
    send_to_slack(j)


def loop(timeout=10):
    no_diff = {'new_services': [],
               'missing_services': [],
               'new_nodes': {},
               'missing_nodes': {}}
    new_services = OrderedDict(sorted(get_services().items()))
    while not new_services:
        new_services = OrderedDict(sorted(get_services().items()))
        services = new_services
        sleep(timeout)
    slack_start(new_services)
    while True:
        new_services = {}
        try:
            new_services = OrderedDict(sorted(get_services().items()))
        except Exception as e:
            logging.error('error getting services: %s' % e)
            send_to_slack({"text": 'error getting services',
                           "attachments": [{
                               "text": '%s' % e,
                               "color": "#cc0000"
                           }]})
            continue
        diff = get_diff_services(old=services, new=new_services)
        if diff == {}:
            # there was en error while connection to consul that should be already handled
            continue
        is_different = False
        for k, v in diff.items():
            if v:
                logging.info('thats different!')
                is_different = True
        logging.debug(diff)
        logging.debug(no_diff)
        if is_different:
            # logging.info('diff in services! new services: %s' % new_services)
            slack_diff(diff)
            services = new_services
        sleep(timeout)


if __name__ == '__main__':
    logging.info('starting!')
    logging.info('using %s' % conf['slack_link'])
    loop()
