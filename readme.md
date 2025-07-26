## Run Emulator

### Check Config File

```firebase.json
{
    "emulators": {
        "auth": {
            "port": 9099
        },
        "functions": {
            "port": 5001
        },
        "database": {
          "port": 9000
        }
    }
}
```

### Start Emulator

```
firebase emulators:start
```