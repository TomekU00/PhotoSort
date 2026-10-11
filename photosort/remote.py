"""Standard OpenSSH transport; no credentials stored."""
import hashlib
import io
import re
import shlex
import subprocess
import zipfile
from pathlib import Path

def bundle():
    import exifread
    import pytz
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, 'w', zipfile.ZIP_DEFLATED) as z:
        z.writestr('__main__.py', 'from photosort.cli import main\nmain()\n')
        for package, name in ((Path(__file__).parent, 'photosort'),
                              (Path(exifread.__file__).parent, 'exifread'),
                              (Path(pytz.__file__).parent, 'pytz')):
            for p in package.rglob('*'):
                if p.is_file() and '__pycache__' not in p.parts and p.suffix != '.pyc':
                    z.write(p, name+'/'+p.relative_to(package).as_posix())
    return buf.getvalue()

def run(args):
    if not re.fullmatch(r'[A-Za-z0-9_.@:-]+', args.host) or args.host.startswith('-'):
        raise ValueError('Nieprawidłowy host SSH')
    if not re.fullmatch(r'[A-Za-z0-9_-]{1,80}', args.job):
        raise ValueError('Nazwa zadania: litery, cyfry, - i _')
    if not args.source.startswith('/') or not args.target.startswith('/'):
        raise ValueError('SSH wymaga bezwzględnych ścieżek serwera')
    data = bundle()
    version = hashlib.sha256(data).hexdigest()[:16]
    base = '"$HOME/.photosort"'
    app = base+'/apps/'+version
    job = base+'/jobs/'+args.job
    if args.status:
        return subprocess.run(['ssh', args.host, 'cat '+job+'/progress.json'], check=True).returncode
    # Upload uses stdin, shell paths contain only validated IDs. SSH asks for password itself.
    subprocess.run(['ssh', args.host, 'umask 077; mkdir -p '+app+' && cat > '+app+'/bundle.zip'], input=data, check=True)
    script = 'import zipfile,sys;zipfile.ZipFile(sys.argv[1]).extractall(sys.argv[2])'
    subprocess.run(['ssh', args.host, 'python3 -c '+shlex.quote(script)+' '+app+'/bundle.zip '+app], check=True)
    flags = ' --job '+job
    if args.resume:
        command = 'python3 '+app+'/__main__.py apply'+flags
    else:
        command = ('python3 '+app+'/__main__.py plan '+shlex.quote(args.source)+' '+shlex.quote(args.target)+flags+
                   ' --format '+shlex.quote(args.pattern)+' --scope '+shlex.quote(args.scope)+' --timezone '+shlex.quote(args.timezone))
        if args.apply:
            command += ' && python3 '+app+'/__main__.py apply'+flags
    # Detach on server; a broken connection or closed PC does not stop the worker.
    code = ('import subprocess,sys,pathlib; j=pathlib.Path(sys.argv[1]);j.mkdir(parents=True,exist_ok=True);'
            'f=(j/"run.log").open("ab");p=subprocess.Popen(["sh","-c",sys.argv[2]],stdin=subprocess.DEVNULL,stdout=f,stderr=f,start_new_session=True);print("PID:",p.pid)')
    subprocess.run(['ssh', args.host, 'python3 -c '+shlex.quote(code)+' '+job+' '+shlex.quote(command)], check=True)
    print('Zadanie działa na serwerze. Log: ~/.photosort/jobs/'+args.job+'/run.log')
    print('Status: photosort remote '+args.host+' '+shlex.quote(args.source)+' '+shlex.quote(args.target)+' --job '+args.job+' --status')
