from ticdat.utils import verify, containerish, stringish, find_duplicates_from_dict_ticdat
from ticdat.utils import find_case_space_duplicates, change_fields_with_reserved_keywords
import ticdat.utils as tu
from ticdat.ticdatfactory import TicDatFactory
import os, subprocess, inspect, time, uuid, shutil
from collections import defaultdict
from ticdat.jsontd import make_json_dict

INFINITY = 999999 # Does AMPL have a way to mark infinity?

ampl_keywords = ["I imagine this will come up eventually"]

def _code_dir():
    return os.path.dirname(os.path.abspath(inspect.getsourcefile(_code_dir)))

def _fix_fields_with_ampl_keywords(tdf):
    return change_fields_with_reserved_keywords(tdf, ampl_keywords)

def _unfix_fields_with_ampl_keywords(tdf):
    return change_fields_with_reserved_keywords(tdf, ampl_keywords, True)

def ampl_run(mod_file, input_tdf, input_dat, soln_tdf, infinity=INFINITY, amplrun_path=None, post_solve=None):
    """
    solve an optimization problem using an AMPL .mod file
    :param mod_file: An AMPL .mod file.
    :param input_tdf: A TicDatFactory defining the input schema
    :param input_dat: A TicDat object consistent with input_tdf
    :param soln_tdf: A TicDatFactory defining the solution schema
    :param infinity: A number used to represent infinity in AMPL
    :return: a TicDat object consistent with soln_tdf, or None if no solution found
    """
    verify(os.path.isfile(mod_file), "mod_file %s is not a valid file."%mod_file)
    verify(not _find_case_space_duplicates(input_tdf), "There are case space duplicate field names in the input schema.")
    verify(not _find_case_space_duplicates(soln_tdf), "There are case space duplicate field names in the solution schema.")
    # Not completely sure this is necessary in AMPL, need to think about it
    verify(len({input_tdf.ampl_prepend + t for t in input_tdf.all_tables}.union(
               {soln_tdf.ampl_prepend + t for t in soln_tdf.all_tables})) ==
           len(input_tdf.all_tables) + len(soln_tdf.all_tables),
           "There are colliding input and solution table names.\nSet ampl_prepend so " +
           "as to insure the input and solution table names are effectively distinct.")
    msg = []
    verify(input_tdf.good_tic_dat_object(input_dat, msg.append),
           "tic_dat not a good object for the input_tdf factory : %s"%"\n".join(msg))
    selected_solver = "some solver path" # I think this is necessary
    orig_input_tdf, orig_soln_tdf = input_tdf, soln_tdf
    input_tdf = _fix_fields_with_ampl_keywords(input_tdf)
    soln_tdf = _fix_fields_with_ampl_keywords(soln_tdf)
    input_dat = input_tdf.TicDat(**make_json_dict(orig_input_tdf, input_dat))
    assert input_tdf.good_tic_dat_object(input_dat)
    mod_file_name = os.path.basename(mod_file)[:-4]
    # I don't think anything needs to be added to the .mod file, I can include the ticdat stuff in the generated .run file
    # with open(mod_file, "r") as f:
    #     mod = f.read()
    #     assert 'writeOutputToFile()' in mod
    #     assert ("ticdat_" + mod_file_name + ".mod") in mod
    #     assert ("ticdat_" + mod_file_name + "_output.mod") in mod
    working_dir = os.path.abspath(os.path.dirname(mod_file))
    if tu.development_deployed_environment:
        working_dir = os.path.join(working_dir, "amplticdat_%s"%uuid.uuid4())
        shutil.rmtree(working_dir, ignore_errors = True)
        os.mkdir(working_dir)
        working_dir = os.path.abspath(working_dir)
        _ = os.path.join(working_dir, os.path.basename(mod_file))
        shutil.copy(mod_file, _)
        mod_file = _
    commandsfile = os.path.join(working_dir, "ticdat_"+mod_file_name+".run")
    datfile = os.path.join(working_dir, "temp.dat")
    output_txt = os.path.join(working_dir, "output.txt")
    results_dat = os.path.join(working_dir, "results.dat")
    if os.path.isfile(results_dat):
        os.remove(results_dat)
    with open(datfile, "w") as f:
        f.write(create_ampl_text(input_tdf, input_dat, infinity))
    verify(os.path.isfile(datfile), "Could not create temp.dat")
    with open(os.path.join(working_dir, "ticdat_"+mod_file_name+".mod"), "w") as f:
        f.write("/* Autogenerated input file, created by ampl.py on " + time.asctime() + " */\n")
        f.write(create_ampl_mod_text(orig_input_tdf))
    with open(os.path.join(working_dir,"ticdat_"+mod_file_name+"_output.mod"), "w") as f:
        f.write("/* Autogenerated output file, created by ampl.py on " + time.asctime() + " */\n")
        f.write(create_ampl_mod_output_text(orig_soln_tdf))
    with open(os.path.join(working_dir,"ticdat_"+mod_file_name+".run"), "w") as f:
        f.write("/* Autogenerated commands file, created by ampl.py on " + time.asctime() + " *\n")
        f.write("model ticdat_"+mod_file_name+".mod;\n") # Not sure if these lines are needed, requires thought
        f.write("model ticdat_"+mod_file_name+"_output.mod;\n")
        f.write("model "+mod_file_name+".mod;\n")
        f.write("data temp.dat;\n")
        f.write("option solver "+selected_solver+";\n")
        f.write("solve;\n")
        for tbn in "output schema":
            f.write("display "+tbn+" > output.txt;\n")
        f.write("close output.txt")
    if not amplrun_path:
        # Maybe check for an environment variable here
        verify(os.path.isfile(os.path.join(_code_dir(),"ampl_run_path.txt")),
               "need to either pass amplrun_path argument or run ampl_run_setup.py")
        with open(os.path.join(_code_dir(),"amplrun_path.txt"),"r") as f:
            amplrun_path = f.read().strip()
    verify(os.path.isfile(amplrun_path), "%s not a valid path to amplrun"%amplrun_path)
    try:
        output = subprocess.check_output([amplrun_path, commandsfile], stderr=subprocess.STDOUT)
    except subprocess.CalledProcessError as err:
        if tu.development_deployed_environment:
            raise Exception("amplrun failed to complete: " + err.output)
        output = err.output
    with open(output_txt, "w") as f:
        f.write(output)
    if not os.path.isfile(results_dat):
        print("%s is not a valid file. A solution was likely not generated. Check 'output.txt' for details."%results_dat)
        return None
    with open(results_dat, "r") as f:
        output = f.read()
    if post_solve:
        post_solve()
    soln_tdf = _unfix_fields_with_ampl_keywords(soln_tdf)
    return read_ampl_text(soln_tdf, output, False)

_can_run_ampl_run_tests = os.path.isfile(os.path.join(_code_dir(),"ampl_run_path.txt"))

def create_ampl_text(tdf, tic_dat, infinity=INFINITY):
    """
    Generate a AMPL .dat string from a TicDat object
    :param tdf: A TicDatFactory defining the schema
    :param tic_dat: A TicDat object consistent with tdf
    :param infinity: A number used to represent infinity in AMPL
    :return: A string consistent with the AMPL .dat format
    """
    msg = []
    verify(tdf.good_tic_dat_object(tic_dat, msg.append),
           "tic_dat not a good object for this factory : %s"%"\n".join(msg))
    verify(not tdf.generator_tables, "doesn't work with generator tables.")
    verify(not tdf.generic_tables, "doesn't work with generic tables. (not yet - will add ASAP as needed) ")
    dict_with_lists = defaultdict(list)
    dict_tables = {t for t,pk in tdf.primary_key_fields.items() if pk}
    for t in dict_tables:
        for k,r in getattr(tic_dat, t).items():
            row = list(k) if containerish(k) else [k]
            for f in tdf.data_fields.get(t, []):
                row.append(r[f])
            dict_with_lists[t].append(row)
    for t in set(tdf.all_tables).difference(dict_tables):
        for r in getattr(tic_dat, t):
            row = [r[f] for f in tdf.data_fields[t]]
            dict_with_lists[t].append(row)

    rtn = "data;\n"
    for i, (t,l) in enumerate(dict_with_lists.items()):
        rtn += "param: %s: "%(tdf.opl_prepend + t) # I don't like using opl_prepend here, should be ampl_pre or tbn_pre
        for field in tdf.data_fields[t]:
            rtn += "\"" + t + "_" + field + "\" "
        rtn += ":=\n"
        for row in l:
            rtn += " "
            for field in row:
                rtn += ("\"%s\""%field if stringish(field) else (str(infinity) if float('inf') == field else str(field))) + " "
            rtn += "\n"
        rtn += ";\n"

    return rtn

def create_ampl_mod_text(tdf):
    """
    Generate a AMPL .mod string from a TicDat object for diagnostic purposes
    :param tdf: A TicDatFactory defining the input schema
    :return: A string consistent with the AMPL .mod input format
    """
    verify(not find_case_space_duplicates(tdf), "There are case space duplicate field names in the schema.")
    verify(not tdf.generator_tables, "Input schema error - doesn't work with generator tables.")
    verify(not tdf.generic_tables, "Input schema error - doesn't work with generic tables. (not yet - will \
            add ASAP as needed) ")
    tdf = _fix_fields_with_ampl_keywords(tdf)
    rtn = ''
    dict_tables = {t for t, pk in tdf.primary_key_fields.items() if pk}
    verify(set(dict_tables) == set(tdf.all_tables), "not yet handling non-PK tables of any sort")

    prepend = getattr(tdf, "ampl_prepend", "")

    def get_table_as_mod_text(tdf, tbn):
        p_tbn = prepend + tbn
        rtn = 'set ' + p_tbn
        if len(tdf.primary_key_fields[tbn]) > 1:
            rtn += ' dimen ' + str(len(tdf.primary_key_fields[tbn]))
        rtn += ';\n'
        for df in tdf.data_fields[tbn]:
            df_m = df.replace(' ', '_').lower()
            rtn += 'param ' + p_tbn + '_' + df_m + ' {' + p_tbn + '};\n'

        # Is this case a thing in ampl?
        # if len(tdf.primary_key_fields[tbn]) is 1 and len(tdf.data_fields[tbn]) is 0:

        return rtn

    for t in dict_tables:
        rtn += get_table_as_mod_text(tdf, t)

    return rtn

# This might make more sense as read_ampl_solution
def read_ampl_text(tdf,text, commaseperator = True):
    """
    Read an AMPL .dat string
    :param tdf: A TicDatFactory defining the schema
    :param text: A string consistent with the AMPL .dat format
    :return: A TicDat object consistent with tdf
    """
    verify(stringish(text), "text needs to be a string")
    # probably want to verify something about the ticdat factory, look at the wiki
    dict_with_lists = defaultdict(list)
    NONE, TBN_DEF, INQUOTES, ROW = 1,2,3,4
    MODE = NONE

    for i,c in enumerate(text):
        # Do things
        pass

    assert not find_duplicates_from_dict_ticdat(tdf, dict_with_lists), \
            "duplicates were found - if asserts are disabled, duplicate rows will overwrite"

    return tdf.TicDat(**{k.replace(tdf.ampl_prepend,"",1):v for k,v in dict_with_lists.items()})

# Look for = signs
