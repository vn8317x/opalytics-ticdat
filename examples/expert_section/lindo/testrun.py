import os, subprocess

if 'TICDAT_LINGO_PATH' not in os.environ:
    raise Exception("Please set the TICDAT_LINGO_PATH environment variable to be the location of runlingo")
assert os.path.isfile(os.environ['TICDAT_LINGO_PATH']), "runlingo not found"

output =''

try:
    output = subprocess.check_output([os.environ['TICDAT_LINGO_PATH'], 'test.ltf'])
except subprocess.CalledProcessError as err:
    with open("err.txt", "w") as f:
        f.write(err)
        raise Exception("Error during runlingo, check err.txt for details")

assert os.path.isfile("SOLU.TXT"), "SOLU.TXT was not generated"
with open("SOLU.TXT") as f:
    assert f.read()[81:89] == '2050.000'

try:
    output = subprocess.check_output([os.environ['TICDAT_LINGO_PATH'], 'tran.ltf'])
except subprocess.CalledProcessError as err:
    with open("err.txt", "w") as f:
        f.write(err)
        raise Exception("Error during runlingo, check err.txt for details")

with open("output.txt", "w") as f:
    f.write(output)

assert output[2236:2241] == '161.0', 'Unexpected output from running tran.ltf, check output.txt'
print "Output completed successfully, check output.txt or see results above"