from os.path import isdir, dirname, isfile
import os
import json
import time


class Server(object):
    INITIAL = 'initial'
    SHUTTING_DOWN = 'replacing'
    TERMINATED = 'terminated'

    def __init__(self, private_ip, instance_id, instance_name, state=INITIAL, completed=False):
        self.private_ip = private_ip
        self.instance_id = instance_id
        self.instance_name = instance_name
        self.state = state
        self.completed = completed

    def __str__(self):
        return '%s (%s): %s' % (self.instance_name, self.instance_id, self.state)


class UpgradeWorkflow(object):
    def __init__(self, controller, cluster_name, servers):
        self.workflow_file = '/tmp/cloud-compose/ecs.upgrade.workflow.%s.json' % cluster_name
        self.controller = controller
        self.curr_index = 0
        self.workflow = self._load_workflow(servers)

    def step(self):
        if self.curr_index >= len(self.workflow):
            print "{} >= {}".format(self.curr_index, len(self.workflow))
            return False

        server = self.workflow[self.curr_index]
        print server

        healthy = self.controller.cluster_health()
        if healthy:
            self._next_step()
        else:
            return True

        # We're done, so cleanup.
        if self.curr_index >= len(self.workflow):
            self._delete_workflow()
            return False
        else:
            return True

    def _next_step(self):
        server = self.workflow[self.curr_index]

        """
        Server.INITIAL => Server.SHUTTING_DOWN => Server.TERMINATED
        """
        if server.state == Server.INITIAL:
            if self.controller.cluster_health():
                # Replace this instance if the cluster is healthy.
                self.controller.replace_instance(server.instance_id)
            server.state = Server.SHUTTING_DOWN
            self._save_workflow()

        elif server.state == Server.SHUTTING_DOWN:
            status = self.controller.instance_status(server.instance_id)
            healthy = self.controller.cluster_health()
            if status == Server.TERMINATED and healthy:
                # Switch to TERMINATED state after the cluster is healthy (node has been replaced)
                server.state = Server.TERMINATED
                self._save_workflow()

        elif server.state in Server.TERMINATED:
            healthy = self.controller.cluster_health()
            if healthy:
                server.completed = True
                self.curr_index += 1
            self._save_workflow()

    def _load_workflow(self, servers):
        workflow = []
        if isfile(self.workflow_file):
            mtime = time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(os.path.getmtime(self.workflow_file)))
            print("Detected a partially completed upgrade on %s." % mtime)
            command = raw_input("Do you want continue this upgrade [yes/no]?: ")
            if command.lower() == 'yes':
                with open(self.workflow_file) as f:
                    data = json.load(f)
                for server in data:
                    server = Server(private_ip=server['private_ip'],
                                    instance_id=server['instance_id'],
                                    instance_name=server['instance_name'],
                                    state=server['state'],
                                    completed=server['completed'])
                    if server.completed:
                        self.curr_index += 1
                    workflow.append(server)

                print "%s" % workflow[self.curr_index]
            else:
                os.remove(self.workflow_file)
        if len(workflow) == 0:
            workflow.extend(servers)
        return workflow

    def _save_workflow(self):
        workflow_dir = dirname(self.workflow_file)
        if not isdir(workflow_dir):
            os.makedirs(workflow_dir)

        with open(self.workflow_file, 'w') as f:
            json.dump(self.toJSON(), f)

    def toJSON(self):
        workflow_list = []
        for server in self.workflow:
            workflow_list.append({
                'private_ip': server.private_ip,
                'instance_name': server.instance_name,
                'instance_id': server.instance_id,
                'state': server.state,
                'completed': server.completed
            })
        return workflow_list

    def _delete_workflow(self):
        if isfile(self.workflow_file):
            os.remove(self.workflow_file)
