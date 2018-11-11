object Different {
    def main(args: Array[String]) {
        var line = scala.io.StdIn.readLine()
        while (line != null) {
            val Array(a, b) = line.split(" ").map(_.toLong)
            val r = scala.math.abs(a - b)
            Console.out.println(r)
            line = scala.io.StdIn.readLine()
        }
    }
}
