from StringIO import StringIO
import subprocess
import re
import tempfile

import yaml


class JujuClient:

    def __init__(self, env_name, debug=False):
        self.env_name = env_name
        self.debug = debug

    def _full_args(self, command, args, timeout=None, include_e=True):
        if self.env_name is None or not include_e:
            e_arg = ()
        else:
            e_arg = ('-e', self.env_name)
        if timeout is None:
            prefix = ()
        else:
            prefix = ('timeout', timeout)
        logging = '--debug' if self.debug else '--show-log'

        # we split the command here so that the caller can control where the -e
        # <env> flag goes.  Everything in the command string is put before the
        # -e flag.
        command = command.split()
        return prefix + ('juju', logging,) + tuple(command) + e_arg + args

    def get_juju_output(self, command, *args, **kwargs):
        """Call a juju command and return the output.

        Sub process will be called as 'juju <command> <args> <kwargs>'. Note
        that <command> may be a space delimited list of arguments. The -e
        <environment> flag will be placed after <command> and before args.
        """
        args = self._full_args(command, args,
                               timeout=kwargs.get('timeout'),
                               include_e=kwargs.get('include_e', True))
        with tempfile.TemporaryFile() as stderr:
            try:
                sub_output = subprocess.check_output(args, stderr=stderr)
                return sub_output
            except subprocess.CalledProcessError as e:
                stderr.seek(0)
                e.stderr = stderr.read()
                if ('Unable to connect to environment' in e.stderr or
                        'MissingOrIncorrectVersionHeader' in e.stderr or
                        '307: Temporary Redirect' in e.stderr):
                    raise CannotConnectEnv(e)
                raise

    def action_fetch(self, id_, action=None, timeout="1m"):
        """Fetches the results of the action with the given id.

        Will wait for up to 1 minute for the action results.
        The action name here is just used for an more informational error in
        cases where it's available.
        Returns the yaml output of the fetched action.
        """
        out = self.get_juju_output("action fetch", id_, "--wait", timeout)
        status = yaml_loads(out)["status"]
        if status != "completed":
            name = ""
            if action is not None:
                name = " " + action
            raise Exception(
                "timed out waiting for action%s to complete during fetch" %
                name)
        return out

    def action_do(self, unit, action, *args):
        """Performs the given action on the given unit.

        Action params should be given as args in the form foo=bar.
        Returns the id of the queued action.
        """
        args = (unit, action) + args
        output = self.get_juju_output("action do", *args)
        action_id_pattern = re.compile(
            'Action queued with id: ([a-f0-9\-]{36})')
        match = action_id_pattern.search(output)
        if match is None:
            raise Exception("Action id not found in output: %s" %
                            output)
        return match.group(1)

    def action_do_fetch(self, unit, action, timeout="3m", *args):
        """Performs given action on given unit and waits for the results.

        Action params should be given as args in the form foo=bar.
        Returns the yaml output of the action.
        """
        id_ = self.action_do(unit, action, *args)
        return self.action_fetch(id_, action, timeout)


class CannotConnectEnv(subprocess.CalledProcessError):

    def __init__(self, e):
        super(CannotConnectEnv, self).__init__(e.returncode, e.cmd, e.output)


def yaml_loads(yaml_str):
    return yaml.safe_load(StringIO(yaml_str))
