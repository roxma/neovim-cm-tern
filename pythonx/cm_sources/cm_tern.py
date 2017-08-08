# -*- coding: utf-8 -*-

# For debugging
# NVIM_PYTHON_LOG_FILE=nvim.log NVIM_PYTHON_LOG_LEVEL=INFO nvim

from cm import register_source, getLogger, Base
register_source(name='cm-tern',
                   priority=9,
                   abbreviation='Js',
                   scoping=True,
                   scopes=['javascript','javascript.jsx'],
                   early_cache=1,
                   word_pattern=r'[\w$\-]+',
                   cm_refresh_patterns=[r'\.'],)

import os
import re
import logging
from neovim import attach, setup_logging
import re
import subprocess
import logging
from urllib import request
import json
import cm
import platform

logger = getLogger(__name__)

class Tern:

    def __init__(self,bin):
        args = [bin, '--persistent', '--no-port-file']
        if platform.system().lower()=='windows':
            args.insert(0,'node')
        elif platform.system().lower()=='linux':
            # nodejs on ubuntu
            import shutil
            nodejs = shutil.which('nodejs')
            if nodejs:
                args.insert(0,nodejs)
        proc = subprocess.Popen(args,
                                stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                stderr=subprocess.DEVNULL
        )
        line = proc.stdout.readline().decode('utf8')
        logger.info('read line: %s', line)

        match = re.match(r'Listening on port (\d+)', line)

        self._port = match.group(1)
        logger.info('port [%s]', self._port)

        self._opener = request.build_opener()

    def completions(self, src, lnum, col, path):

        """
        :lnum: lnum zero based
        :col: col zero based
        """

        doc = {"query": {}, "files": []}
        query = doc['query']
        query['type'] = 'completions'
        query["file"] = '#0'
        query["end"] = dict(line=lnum,ch=col)

        query['lineCharPositions'] = True
        # query['expandWordForward'] = True
        query['includeKeywords'] = True
        query['caseInsensitive'] = True
        query['docs'] =  True
        query['urls'] =  True
        # type informations on completion items
        query['types'] =  True

        files = doc['files']
        files.append({"type": "full",
                      "name": path,
                      "text": src})

        return self.request(doc)

    def request(self, doc):

      try:
          payload = json.dumps(doc).encode('utf-8')
          logger.info('payload: %s', payload)
          req = self._opener.open("http://127.0.0.1:" + str(self._port) + "/", payload)
          result = req.read().decode('utf-8')
          logger.info('result: %s', result)
          return json.loads(result)
      except Exception as ex:
          logger.exception('exception: %s, %s', ex, doc)
          return None


class Source(Base):

    def __init__(self,nvim):
        super(Source,self).__init__(nvim)

        logger.info('eval for tern: %s', 'split(globpath(&rtp,"node_modules/tern/bin/tern",1),"\\n")[0]')
        path = nvim.eval('split(globpath(&rtp,"node_modules/tern/bin/tern",1),"\\n")[0]')
        self._tern = Tern(path)
        logger.info('eval result: %s', path)

    def cm_refresh(self,info,ctx,*args):

        lnum = ctx['lnum']
        typed = ctx['typed']
        path = ctx['filepath']

        src = self.get_src(ctx)

        completions = self._tern.completions(src,lnum-1,len(typed),path)
        logger.info('completions %s, typed[%s], %s', completions,typed,ctx)

        if not completions or not completions.get('completions',None):
            return

        matches = []

        for complete in completions['completions']:

            # {
            #     "name": "copyWithin",
            #     "type": "fn(target: number, start: number, end?: number)",
            #     "doc": "The copyWithin() method copies the sequence of array elements within the array to the position starting at target.",
            #     "url": "https://developer.mozilla.org/en-US/docs/Web/JavaScript/Reference/Global_Objects/Array/copyWithin"
            # }
 
            item = dict(word=complete['name'],
                        icase=1,
                        dup=1,
                        menu=complete.get('type',''),
                        info=complete.get('doc',''),
                        )

            matches.append(item)

            # snippet support
            if 'type' in complete:
                m = re.search(r'fn\((.*?)\)',complete['type'])
                if not m:
                    continue
                params = m.group(1)
                params = params.split(',')
                logger.info('snippet params: %s',params)
                snip_params = []
                num = 1
                for param in params:
                    param = param.strip()
                    if not param:
                        logger.error("failed to process snippet for item: %s, param: %s", item, param)
                        break
                    name = param.split(':')[0]
                    snip_params.append("${%s:%s}" % (num,name))
                    num += 1

                optional = ''
                if not snip_params and params:
                    # There's optional args, don't jump out of parentheses
                    optional = '${1}'

                item['snippet'] = typed + item['word'] + '(' + ", ".join(snip_params) + optional + ')${0}'

        # cm#complete(src, context, startcol, matches)
        ret = self.nvim.call('cm#complete', info['name'], ctx, ctx['startcol'], matches)
        logger.info('matches %s, ret %s', matches, ret)

