from json import load
from static.config import text_json_file_path, text_mlw_file_path
from util.mlw_tools import MLWText, mlw_load

# open .json file with texts
with open(text_json_file_path, 'r', encoding='UTF-8') as json_file:
    # open .mlw file with texts
    with open(text_mlw_file_path, 'r', encoding='UTF-8') as mlw_file:
        # load mlw contents
        mlw_text = mlw_load(mlw_file)
        # load json contents
        json_text = load(json_file)

        # currently only russian language is supported
        data = {'ru': {}}

        # convert json to mlw and push into dict
        for language, text in json_text.items():
            for key, value in text.items():
                data[language][key] = MLWText(key, [value])

        # push mlw into dict
        for key, value in mlw_text.items():
            data['ru'][key] = value


def get_text(name, language_code) -> MLWText:
    """
    returns MLWText for specified name and language_code
    'text' names should end with _text, 'button' name with _button
    """
    if language_code not in data:
        # default language code
        language_code = 'ru'
    retval = data.get(language_code).get(name)
    if retval is None:
        raise ValueError(f'Undefined text name: {name}')
    return retval
