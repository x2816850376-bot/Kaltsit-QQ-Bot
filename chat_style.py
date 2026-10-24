"""Normalize bot-authored chat punctuation while preserving literal content."""
import re

PROTECTED = re.compile(r'```[\s\S]*?```|`[^`\n]+`|“[^”]*”|「[^」]*」|『[^』]*』|"[^"\n]*"|https?://[^\s<>，。！？；：、（）“”「」『』]+')

def normalize_outgoing_text(text):
    protected={match.start():match.end() for match in PROTECTED.finditer(text)}
    output=[]
    index=0
    while index<len(text):
        if index in protected:
            end=protected[index];output.append(text[index:end]);index=end;continue
        char=text[index]
        rest=text[index+1:].lstrip(' \t')
        if char=='。':
            if rest and not rest.startswith(('\n','\r','？','?','！','!','，',',','；',';',':','：')):
                # The user's chat preference omits bubble-final stops, not
                # sentence boundaries inside a longer message.
                output.append('。')
        elif char=='.' and (not rest or rest.startswith(('\n','\r'))):
            # Preserve ellipses and numeric/version notation; inline code and URLs
            # are already protected. Ordinary English sentence stops are removed.
            if index and (text[index-1]=='.' or text[index-1].isdigit()):output.append(char)
        else:output.append(char)
        index+=1
    return ''.join(output)
