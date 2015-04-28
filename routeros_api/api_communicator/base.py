from routeros_api import exceptions
from routeros_api import sentence
from routeros_api import query


class ApiCommunicatorBase(object):
    def __init__(self, base):
        self.base = base
        self.tag = 0
        self.response_buffor = {}

    def send(self, path, command, arguments=None, queries=None,
                   additional_queries=()):
        tag = self._get_next_tag()
        command = self.get_command(path, command, arguments, queries, tag=tag,
                                   additional_queries=additional_queries)
        self.send_command(command)
        self.response_buffor[tag] = AsynchronousResponseCollector(
            command)
        return tag

    def get_command(self, path, command, arguments=None, queries=None,
                     tag=None, additional_queries=()):
        arguments = arguments or {}
        queries = queries or {}
        command = sentence.CommandSentence(path, command, tag=tag)
        for key, value in arguments.items():
            command.set(key, value)
        for key, value in queries.items():
            command.filter(query.IsEqualQuery(key, value))
        for additional_query in additional_queries:
            command.filter(additional_query)
        return command

    def send_command(self, command):
        self.base.send_sentence(command.get_api_format())

    def _get_next_tag(self):
        self.tag += 1
        return str(self.tag).encode()

    def receive(self, tag):
        response = self.response_buffor[tag]
        while(not response.done):
            self.process_single_response()
        del(self.response_buffor[tag])
        if response.error:
            message = "Error \"{error}\" executing command {command}".format(
                error=response.error.decode(), command=response.command)
            raise exceptions.RouterOsApiCommunicationError(
                message, response.error)
        else:
            return response.attributes

    def process_single_response(self):
        response = self.receive_single_response()
        response.save_to_buffor(self.response_buffor)

    def receive_single_response(self):
        serialized = []
        while not serialized:
            serialized = self.base.receive_sentence()
        response_sentence = sentence.ResponseSentence.parse(serialized)
        return SingleResponse(response_sentence)


class SingleResponse(object):
    def __init__(self, response_sentence):
        self.response = response_sentence

    def save_to_buffor(self, buffor):
        if self.response.tag not in buffor:
            raise exceptions.FatalRouterOsApiError(
                "Unknown tag %s", self.response.tag)
        asynchronous_response = buffor[self.response.tag]
        if self.response.type == b're':
            attributes = self.response.attributes
            asynchronous_response.attributes.append(attributes)
        if self.response.type == b'done':
            asynchronous_response.done = True
            attributes = self.response.attributes
            asynchronous_response.attributes.done_message = attributes
        elif self.response.type == b'trap':
            asynchronous_response.error = self.response.attributes[b'message']
        elif self.response.type == b'fatal':
            del(buffor[self.response.tag])
            message = "Fatal error executing command {command}".format(
                command=asynchronous_response.command)
            raise exceptions.RouterOsApiFatalCommunicationError(message)


class AsynchronousResponseCollector(object):
    def __init__(self, command):
        self.attributes = AsynchronousResponse()
        self.done = False
        self.error = None
        self.command = command


class AsynchronousResponse(list):
    def __init__(self, *args, **kwargs):
        super(AsynchronousResponse, self).__init__(*args, **kwargs)
        self.done_message = {}

    def map(self, function):
        result = type(self)(function(item) for item in self)
        result.done_message = function(self.done_message)
        return result
