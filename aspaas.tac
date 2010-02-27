#!/usr/bin/python

from twisted.application import service, internet
from twisted.internet import reactor, protocol, defer
from twisted.web import server, resource, static
from twisted.python import log
import simplejson
import os, signal

class RequestedProcessProtocol(protocol.ProcessProtocol):
  def __init__(self, input, request):
    self.input = input
    self.request = request
    self.json = 'json' in request.args
    if self.json:
      self.leftovers = ''
    self.padding = request.args.get('jsonp',[None])[0]

  def connectionMade(self):
    self.transport.write(self.input)
    self.transport.closeStdin()
    self.request.setHeader('Content-type','text/plain')

  def outReceived(self, data):
    if self.json:
      self.leftovers += data
      parts = self.leftovers.split("\n")
      self.leftovers = parts[-1]
      map(self.encode, parts[:-1])
    else:
      self.request.write(data)
      

  def errReceived(self, data):
    if not self.json:
      self.request.write(data)
 
  def outConnectionLost(self):
    self.request.finish()

  def stop(self):
    if self.transport.pid is not None:
      cmd = "pkill -9 -P %d" % self.transport.pid
      os.system(cmd)

  def encode(self, line):
    def intify(val):
      if val.isdigit():
        return int(val);
      else:
        return val
    if line.startswith("Stable Model:"):
      guts = line.replace("Stable Model:","").strip()
      facts = guts.split(" ")
      model = {}
      for fact in facts:
        if "(" in fact:
          # assumes no function terms
          head, args = fact.strip(")").split("(")
          model[head] = model.get(head,[]) + [map(intify,args.split(","))]
        elif fact:
          model[fact] = True
      if self.padding:
        self.request.write("%s(%s);\r" % (self.padding, simplejson.dumps(model)))
      else:
        self.request.write("%s\r" % simplejson.dumps(model))

def launchProcessForRequest(executable, args, input, request):
  arg_list = filter(bool, [executable] + args.split(' '))
  proto = RequestedProcessProtocol(input, request)
  reactor.spawnProcess(
                  proto,
                  executable,
                  arg_list)
  return proto

class SolveResource(resource.Resource):
  def render(self, request):
    args = request.args.get('args',[''])[0]
    code = request.args.get('code',[''])[0]
    request.notifyFinish().addBoth(self.finished)
    self.proto = launchProcessForRequest('./lpsmodels.sh', args, code, request)
    return server.NOT_DONE_YET
  def finished(self, result):
    self.proto.stop()

class BaseResource(resource.Resource):
  def render(self, request):
    return """
      <html>
        <head>
          <title>ASPaaS - Answer Set Programming as a Service</title>
          <style>
            body {
              font-family: sans-serif;
              background-color: #444;
              background-image: url("lparse.png");
              background-repeat: no-repeat;
              color: #bbb;
            } 
            h1, h2 {
              color: #eee;
            }
            a { color: white; }
            textarea, input {
              display: block;
              background-color: rgba(0,0,0,0.5);
              color: #8f8;
              border-width: 2px;
              border-top: solid #000;
              border-left: solid #000;
              border-bottom: solid #666;
              border-right: solid #666;
              margin-top: 5px;
              margin-bottom: 20px;
              font-family: monospace;
              -moz-border-radius: 10px;
            }
            input[type="submit"]  {
              background-color: white;
              color: black;
              font-weight: bold;
            }
            p {
              width: 40em;
            }
          </style>
        </head>
        <body>
          <h1>Answer-Set Programming for the Web</h1>
          <p>
          The program you enter below will be piped into <tt>lparse</tt> with the
          arguments you provide and the resulting problem will be piped to
          <tt>smodels</tt> using <code>-seed $RANDOM</code> as its only
          arguments. Consult <a
          href="lparse.pdf">lparse.pdf</a>
          for details of the input language and argument specs.
          </p>
          <p>
          Options are
          available for formatting the resulting models as either a JSON or
          JSONP stream which can be aborted at any time.
          </p>
          <h2>Program Input</h2>
          <form action="/solve" method="POST" id="driver">
            <label for="code">Lparse program:</label>
            <textarea rows="20" cols="80" name="code"></textarea>
            <label for="args">Lparse arguments:</label>
            <input type="text" name="args" size="80" />
            <label for="json">JSON encoding:</label>
            <input type="checkbox" name="json" />
            <label for="jsonp">JSON padding:</label>
            <input type="text" name="jsonp" size="10" />
            <input type="submit" value="Solve" />
          </form>
        </body>
      </html>
      """

root = resource.Resource()
root.putChild('', BaseResource())
root.putChild('solve', SolveResource())
root.putChild('lparse.png', static.File('lparse.png'))
root.putChild('lparse.pdf', static.File('lparse.pdf'))
root.putChild('crossdomain.xml', static.File('crossdomain.xml'))

port = 8118

application = service.Application("ASPaaS")
service = internet.TCPServer(port, server.Site(root))
service.setServiceParent(application)
