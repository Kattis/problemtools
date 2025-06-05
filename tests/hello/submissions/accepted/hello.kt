fun main(args: Array<String>) {
  val words = if (args.size == 0) arrayOf("Hello", "World!") else args
  System.`out`.println(words.joinToString(separator = " "))
}
