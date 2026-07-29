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
  # Heap/metaspace/code-cache are bounded explicitly. Without cgroups judge0
  # enforces memory as RLIMIT_AS, but the JVM sizes its heap and metaspace from
  # *physical* RAM, so an unbounded JVM asks for ~1 GB heap + 1 GB metaspace and
  # dies with "Could not reserve enough space for ... object heap" no matter how
  # high the limit is raised. javac is itself a JVM, so it needs the same bounds
  # via -J. This mirrors the hotfix the existing CAP GCP deployment applies to
  # language 62 at runtime.
  {
    id: 62,
    name: "Java (OpenJDK)",
    is_archived: false,
    source_file: "Main.java",
    compile_cmd: "/usr/bin/javac -J-Xms16m -J-Xmx128m -J-XX:+UseSerialGC -J-XX:CompressedClassSpaceSize=32m -J-XX:MaxMetaspaceSize=128m -J-XX:ReservedCodeCacheSize=32m %s Main.java",
    run_cmd: "/usr/bin/java -Xms16m -Xmx128m -XX:+UseSerialGC -XX:CompressedClassSpaceSize=32m -XX:MaxMetaspaceSize=128m -XX:ReservedCodeCacheSize=32m Main"
  },
  {
    id: 1003,
    name: "Java (OpenJDK, CAP bounded heap)",
    is_archived: false,
    source_file: "Main.java",
    compile_cmd: "/usr/bin/javac -J-Xms16m -J-Xmx64m -J-XX:+UseSerialGC -J-XX:CompressedClassSpaceSize=32m -J-XX:MaxMetaspaceSize=96m -J-XX:ReservedCodeCacheSize=32m %s Main.java",
    run_cmd: "/usr/bin/java -Xms16m -Xmx64m -XX:+UseSerialGC -XX:CompressedClassSpaceSize=32m -XX:MaxMetaspaceSize=96m -XX:ReservedCodeCacheSize=32m Main"
  },
  {
    id: 71,
    name: "Python (3)",
    is_archived: false,
    source_file: "script.py",
    run_cmd: "/usr/bin/python3 script.py"
  },
  {
    id: 63,
    name: "JavaScript (Node.js)",
    is_archived: false,
    source_file: "script.js",
    run_cmd: "/usr/bin/node script.js"
  }
]
