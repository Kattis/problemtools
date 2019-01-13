import java.io.*;
import java.util.*;

public class guess {
	public static void main(String[] args) {
		Scanner scanner = new Scanner(System.in);
		int alpha = 1, omega = 1000;
		while (true) {
			int mid = (alpha + omega)/2;
			System.out.println(mid);
			String response = scanner.next();
			switch (response) {
				case "correct":
					System.exit(0);
				case "lower":
					omega = mid -1;
					break;
				default:
					alpha = mid + 1;
			}
		}
	}
}
