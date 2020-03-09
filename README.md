### stdf2XML

In order to convert an STDF file into an XML one, you'll need to build the image:

```bash
docker build -t username/stdf2xml .
```

and then run using the following command:

```bash
docker run -v <full_path.stdf>:/ind.stdf username/stdf2xml ./stdf2xml /ind.stdf > output.xml
```
