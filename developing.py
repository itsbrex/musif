import sys

sys.path.insert(0, "../musif")
sys.path.insert(0, "../musif/musif") 
from musif.extract.extract import FeaturesExtractor, FilesValidator
from musif.reports.generate import FeaturesGenerator
import pandas as pd


if __name__ == "__main__":
 
    data_dir = r'tests/data/static/features'
    musescore_dir=data_dir

    data_dir = r'../../_Ana/Music Analysis/xml/corpus_github\xml/Ale12M-Non_sarei-nd-Anonymous[2.04][1239].xml'
    musescore_dir = r'../../_Ana\Music Analysis/xml/corpus_github/musescore'

    # data_dir = r'../Corpus_175/xml/Ale02M-Vedrai_con-1772-Anfossi[1.02][0811].xml'
    # musescore_dir =  r'../Corpus_175/musescore'
    
    #reference
    # data_dir = r'../../_Ana/Music Analysis/xml/corpus_github\xml/Did03M-Son_regina-1724-Sarro[1.05][0001].xml'


    df = FeaturesExtractor("config_tests.yml", data_dir=data_dir, musescore_dir=musescore_dir).extract()

    # df.to_csv('test.csv', index=False)
    # df=pd.read_csv('martiser/dataframe.csv')
    # path = './'
    # FeaturesGenerator("martiser/myconfig.yml").generate_reports(df, path, num_factors=1, visualizations=True)
    pass