package main

import (
	"fmt"
	"time"
)

func main() {
	fmt.Println("Hello, World!666666")
	// %d 表示整型数字，%s 表示字符串
	var stockcode = 123
	var enddate = "2020-12-31"
	var LLYtime = time.Now()

	var url = "Code=%d&endDate=%s"
	var target_url = fmt.Sprintf(url, stockcode, enddate)
	fmt.Println(target_url)
	fmt.Println("LLYtime is", LLYtime)

}
