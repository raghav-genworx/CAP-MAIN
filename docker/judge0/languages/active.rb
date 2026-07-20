@languages ||= []
@languages += [
  {
    id: 50,
    name: "C (GCC)",
    is_archived: false,
    source_file: "main.c",
    compile_cmd: "/usr/bin/gcc %s main.c",
    run_cmd: "./a.out"
  },
  {
    id: 54,
    name: "C++ (G++)",
    is_archived: false,
    source_file: "main.cpp",
    compile_cmd: "/usr/bin/g++ %s main.cpp",
    run_cmd: "./a.out"
  },
  {
    id: 62,
    name: "Java (OpenJDK)",
    is_archived: false,
    source_file: "Main.java",
    compile_cmd: "/usr/bin/javac %s Main.java",
    run_cmd: "/usr/bin/java -Xms16m -Xmx128m -XX:+UseSerialGC Main"
  },
  {
    id: 71,
    name: "Python (3)",
    is_archived: false,
    source_file: "script.py",
    run_cmd: "/usr/bin/python3 script.py"
  }
]
