import contextlib
import copy
import os
import subprocess
import tempfile
from typing import List

import pandas as pd

import musif.extract.constants as C
from musif.config import ExtractConfiguration
from musif.extract.features.jsymbolic.utils import (_jsymbolic_path,
                                                    get_java_path)
from musif.logs import pwarn

JSYMBOLIC_JAR = str(_jsymbolic_path())
JAVA_PATH = get_java_path()


def get_tmpdir():
    if os.path.exists("/dev/shm"):
        return tempfile.TemporaryDirectory(dir="/dev/shm")
    else:
        return tempfile.TemporaryDirectory()


def write_midi(score, midi_path):
    bytes = score.toData('midi') 
    with open(midi_path, 'wb') as f:
        f.write(bytes)


def update_score_objects(
    score_data: dict,
    parts_data: List[dict],
    cfg: ExtractConfiguration,
    parts_features: List[dict],
    score_features: dict,
):
    score = score_data["score"]
    # 1. create a temporary directory (if Linux, force RAM usig /dev/shm)
    with get_tmpdir() as tmpdirname:
        # 2. convert the score to MEI usiing music21
        midi_path = os.path.abspath(os.path.join(tmpdirname, "score.midi"))
        if cfg.jsymbolic_remove_repeats:
            score_without_repeats, _ = _remove_repetitions_from_score(score)
            write_midi(score_without_repeats, midi_path)
        else:
            try:
                write_midi(score, midi_path)
            except Exception as e:
                filename = score_data[C.DATA_FILE]
                if cfg.jsymbolic_try_without_repeats:
                    score_without_repeats, found = _remove_repetitions_from_score(score)
                    if found:
                        try:
                            write_midi(score_without_repeats, midi_path)
                        except Exception as e:
                            pwarn(f"jsymbolic: could not convert {filename} to MIDI: {e}")
                            return
                if not cfg.jsymbolic_try_without_repeats or not found:
                    pwarn(f"jSymbolic: could not convert {filename} to MIDI or process repetitions correctly: {e}")
                    return

        # 3. run the MEI file through the jSymbolic jar saving csv into the temporary
        # directory in RAM
        out_path = os.path.abspath(os.path.join(tmpdirname, "features"))
        cmd = [
            JAVA_PATH,
            f"-Xmx{cfg.jsymbolic_max_ram}",
            "-jar",
            JSYMBOLIC_JAR,
            "-csv",
        ]
        if cfg.jsymbolic_config_file is not None:
            cmd += ["-configrun", cfg.jsymbolic_config_file]
        try:
            subprocess.run(
                cmd
                + [
                    midi_path,
                    out_path + ".xml",
                    out_path + "_def.xml",
                ],
                check=True,
                stdout=subprocess.DEVNULL,
            )
        except Exception as e:
            pwarn(f"jSymbolic: cannot run jSymbolic on {filename}: {e}. Trying again without repeat marks.")
            score_without_repeats, found = _remove_repetitions_from_score(score)
            if found:
                try:
                    write_midi(score_without_repeats, midi_path)
                except Exception as e:
                    pwarn(f"jsymbolic: could not convert {filename} to MIDI: {e}")
                    return
            subprocess.run(
                cmd
                + [
                    midi_path,
                    out_path + ".xml",
                    out_path + "_def.xml",
                ],
                check=True,
                stdout=subprocess.DEVNULL,
            )        
        filename = score_data[C.DATA_FILE]

        try:
            df = pd.read_csv(out_path + ".csv", na_values=["NaN", " NaN", "NaN ", " NaN "])
            df = df.drop(columns = df.columns[0])
            df.columns = ["js_" + c for c in df.columns] # 5. add `js_` prefix to the column names
            # 6. load the features into the score_features dictionary
            score_features.update(df.to_dict(orient="records")[0])
        except Exception as e:
            pwarn(f"jSymbolic fetures failed run jSymbolic on {filename}: {e}")
            return
        
def _remove_repetitions_from_score(score):
    score_without_repeats = copy.deepcopy(score)
    found = False
    for el in score.recurse().getElementsByClass("RepeatMark"):
        found = True
        # WARNING! this is not campatible with the cache system!
        score.remove(el, recurse=True)
    return score_without_repeats, found


def update_part_objects(
    score_data: dict, part_data: dict, cfg: ExtractConfiguration, part_features: dict
):
    pass
