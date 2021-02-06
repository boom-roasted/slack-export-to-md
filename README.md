# Slack export --> markdown

1. Choose channel to consolidate
2. Read channel information into threads
3. Output thread conversations in markdown format

### Example usage
The following command will read the slack export files in a folder named 'export' and will process all channels that begin with the text 'help'.
```console
# python main.py export/ "help*"
```
